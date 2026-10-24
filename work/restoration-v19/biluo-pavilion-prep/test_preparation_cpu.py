"""Small meaningful CPU preflight and complete-domain tests; no bpy import."""
import copy
import json
import math
from types import SimpleNamespace
import unittest

from shapely.geometry import Polygon, Point

import prepare_biluo_profile as Q


class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p,cls.palette,cls.report=Q.make();cls.v=Q.validator()
        cls.mats={k:SimpleNamespace(name='CPU_'+k) for k in cls.palette['materials']}

    def test_TS01_fact_source_full_frame(self):
        p=self.p;fields=Q.read('work/restoration-v19-preparation/facts-and-candidates.json')['entities']['biluoting']['fields']
        self.assertEqual(p['known_facts'],fields);self.assertEqual(p['roof_profile']['known_facts'],fields)
        self.assertEqual(len(p['source_polygon_local']),7);self.assertEqual(p['source_holes_local'],[])
        self.assertIsNone(p['known_facts']['mountain_support_apex_z_m']['value'])
        self.assertIsNone(p['known_facts']['occupied_storeys']['value'])
        self.assertFalse(p['mountain_is_reconstructed']);self.assertEqual(p['allowed_hidden_source_actor_names'],[])
        self.v._validate(p,self.mats)

    def test_TS02_actual_seven_polygon_source_contains_entire_roof_disk(self):
        domain=Polygon(self.p['source_polygon_local'])
        disk=Point(0,0).buffer(2.22,resolution=256)
        self.assertTrue(domain.covers(disk));self.assertGreater(domain.boundary.distance(disk),.08)
        self.assertAlmostEqual(self.v._inradius(self.p['source_polygon_local']),2.3035899125165717)

    def test_TS03_complete_column_and_lower_cap_domains(self):
        p=self.p;rp=p['roof_profile'];n=5*rp['segments_per_sector'];phase=rp['phase_rad'];t=rp['roof_tiers'][0]
        # Explicit sampled polygon matches the frozen roof tessellation's actual
        # control-ring input, but remains CPU preflight rather than actual mesh.
        ring=[];outer=[]
        for i in range(n):
            a=i*2*math.pi/n;wave=.5*(1-math.cos(5*a))
            for target,r in ((ring,t['inner_radius_m']+t['inner_lobe_amplitude_m']*wave),(outer,t['outer_radius_m']+t['lobe_amplitude_m']*wave)):
                target.append((r*math.cos(a+phase),r*math.sin(a+phase)))
        hole=Polygon(ring);skin=Polygon(outer,[ring]);d=p['study']
        for i,(x,y) in enumerate(self.v._axes(p)):
            column=Polygon(self.v._circle(x,y,d['column_radius_m']))
            self.assertTrue(hole.covers(column));self.assertGreater(hole.boundary.distance(column),.079)
            a=phase+i*2*math.pi/5;b=(1.45*math.cos(a),1.45*math.sin(a))
            cap=Polygon(self.v._circle(*b,.1));self.assertTrue(skin.covers(cap))
            # Actual builder beam is centered on axis endpoints and adds one
            # beam-width to length: both ends extend by half width.
            u=(math.cos(a),math.sin(a));v=(-u[1],u[0]);lo=.8-.13;hi=1.45+.13
            beam=Polygon([(r*u[0]+sign*.13*v[0],r*u[1]+sign*.13*v[1]) for r,sign in ((lo,-1),(hi,-1),(hi,1),(lo,1))])
            self.assertTrue(beam.covers(cap));self.assertGreater(beam.intersection(column).area,0)

    def test_TS04_no_fake_occupied_storey(self):
        self.assertIsNone(self.p['occupied_storeys']);self.assertEqual(self.p['reference_floor_count'],1)
        self.assertEqual(self.p['roof_profile']['reference_floor_count'],0)
        self.assertEqual(self.p['study']['lower_beam_top_z_m'],5.1)
        self.assertLess(5.1,self.p['roof_profile']['roof_tiers'][0]['eave_z_m']-.1)
        self.assertGreater(self.p['study']['upper_beam_top_z_m'],self.p['roof_profile']['roof_tiers'][0]['top_z_m'])

    def test_EXTRA01_piercing_columns_and_cross_hole_caps_rejected(self):
        for key,value in (('column_axis_radius_m',.95),('lower_bearing_axis_radius_m',1.0),('beam_width_m',.18)):
            p=copy.deepcopy(self.p);p['study'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.v._validate(p,self.mats)

    def test_EXTRA02_metric_and_money_boundaries(self):
        for value in (0,-1,True,math.inf,math.nan):
            p=copy.deepcopy(self.p);p['study']['column_radius_m']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.v._validate(p,self.mats)
        for value in (-1,1,0.0,True):
            p=copy.deepcopy(self.p);p['third_party_cost']=value
            with self.subTest(cost=value),self.assertRaises(ValueError):self.v._validate(p,self.mats)

    def test_EXTRA03_source_overflow_and_source_trimming_rejected(self):
        p=copy.deepcopy(self.p);p['roof_profile']['roof_tiers'][0]['outer_radius_m']=2.3
        with self.assertRaises(ValueError):self.v._validate(p,self.mats)
        p=copy.deepcopy(self.p);p['source_polygon_local']=p['source_polygon_local'][:5]
        with self.assertRaises(ValueError):self.v._validate(p,self.mats)

    def test_EXTRA04_unknown_promotion_and_fake_floor_count_rejected(self):
        p=copy.deepcopy(self.p);p['reference_floor_count']=2
        with self.assertRaises(ValueError):self.v._validate(p,self.mats)
        p=copy.deepcopy(self.p);p['known_facts']['mountain_support_apex_z_m']['value']=7
        with self.assertRaises(ValueError):self.v._validate(p,self.mats)
        p=copy.deepcopy(self.p);p['occupied_storeys']=2
        with self.assertRaises(ValueError):self.v._validate(p,self.mats)

    def test_EXTRA06_whole_actual_contact_plane_checker(self):
        import check_actual_domains as C
        vertices=[[-.2,-.2,0],[.2,-.2,0],[.2,.2,0],[-.2,.2,0],
                  [-.2,-.2,1.96],[.2,-.2,2.04],[.2,.2,2.04],[-.2,.2,1.96]]
        faces=[[0,2,1],[0,3,2],[4,5,6],[4,6,7]]
        cap={'vertices':vertices,'triangles':faces,'triangle_materials':[0]*4}
        roof={'vertices':[[-1,-1,1.8],[1,-1,2.2],[1,1,2.2],[-1,1,1.8]],
              'triangles':[[0,2,1],[0,3,2]],'triangle_materials':[0,0]}
        records=[{'object':'cap','roof':'roof','bottom_z_m':0}]
        evidence=C.contacts({'cap':cap,'roof':roof},records)
        self.assertAlmostEqual(evidence[0]['actual_complete_top_area_m2'],.16)
        bad=copy.deepcopy(cap);bad['vertices'][6][2]+=.01
        with self.assertRaisesRegex(AssertionError,'roof underside'):
            C.contacts({'cap':bad,'roof':roof},records)

    def test_EXTRA07_contact_full_domain_catches_interior_hole_with_valid_corners(self):
        import check_actual_domains as C
        cap={'vertices':[[-.2,-.2,0],[.2,-.2,0],[.2,.2,0],[-.2,.2,0],
                         [-.2,-.2,2],[.2,-.2,2],[.2,.2,2],[-.2,.2,2]],
             'triangles':[[0,2,1],[0,3,2],[4,5,6],[4,6,7]],'triangle_materials':[0]*4}
        vertices=[];faces=[]
        # All cap corners meet this actual planar mesh; its central gap still
        # leaves part of the cap unsupported and must fail whole-domain checks.
        for x0,y0,x1,y1 in ((-1,-1,1,-.05),(-1,.05,1,1),(-1,-.05,-.05,.05),(.05,-.05,1,.05)):
            base=len(vertices);vertices.extend([[x0,y0,2],[x1,y0,2],[x1,y1,2],[x0,y1,2]])
            faces.extend([[base,base+2,base+1],[base,base+3,base+2]])
        roof={'vertices':vertices,'triangles':faces,'triangle_materials':[0]*8}
        with self.assertRaisesRegex(AssertionError,'roof underside'):
            C.contacts({'cap':cap,'roof':roof},[{'object':'cap','roof':'roof','bottom_z_m':0}])

    def test_EXTRA08_reference_support_floor_Z_chain_and_gap(self):
        import check_actual_domains as C
        components={'source_support_reference':['support'],'source_reference_floor':['floor']}
        def prism(lo,hi):
            return {'vertices':[(-1,-1,lo),(1,-1,lo),(1,1,lo),(-1,1,lo),(-1,-1,hi),(1,-1,hi),(1,1,hi),(-1,1,hi)],
                    'triangles':[[0,2,1],[0,3,2],[4,5,6],[4,6,7]],'triangle_materials':[0]*4}
        geometry={'support':prism(0,2.4),'floor':prism(2.4,2.6)}
        evidence=C.reference_chain(geometry,self.p,components)
        self.assertEqual(evidence['actual_vertical_gap_m'],0)
        geometry['support']=prism(-.1,2.3)
        with self.assertRaisesRegex(AssertionError,'support Z'):
            C.reference_chain(geometry,self.p,components)

    def test_TS05_upper_visual_proportions_are_study_and_keep_clearance(self):
        lower,upper=self.p['roof_profile']['roof_tiers'];v=self.p['parameter_evidence']['upper_visual_proportions']
        self.assertEqual(v['status'],'unmeasured_study')
        self.assertAlmostEqual(upper['top_z_m']-upper['eave_z_m'],.70)
        self.assertAlmostEqual(upper['eave_z_m']-lower['top_z_m'],.50)
        self.assertGreater(upper['eave_z_m']-upper['skin_thickness_m'],lower['top_z_m']+lower['ridge_offset_m']+lower['ridge_radius_m'])
        self.assertIsNone(self.p['known_facts']['total_height_m']['value'])
        self.v._validate(self.p,self.mats)

    def test_EXTRA05_determinism_and_no_bpy_loaded(self):
        import sys
        self.assertNotIn('bpy',sys.modules)
        self.assertEqual(self.p,json.loads((Q.HERE/'profile-v2.json').read_text()))
        for rel,pin in Q.FROZEN_PINS.items():self.assertEqual(Q.sha(Q.ROOT/rel),pin)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PreparationTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--report',default='CPU-preparation-tests-01.json');args=parser.parse_args()
    report=(Q.HERE/args.report).resolve();Q.require(report.parent==Q.HERE,'Report must stay inside local preparation directory')
    Q.write(report,{'schema':'v19-biluo-CPU-preparation-tests/1','run':result.testsRun,
        'passed':result.testsRun-len(result.failures)-len(result.errors),'failed':len(result.failures),'errors':len(result.errors),
        'details':[str(t)+'\n'+detail for t,detail in result.failures+result.errors],
        'test_sha256':Q.sha(__file__),'Blender_started':False,'actual_new_assembly_verified':False,'third_party_cost':0,'human_approval':'pending'})
    raise SystemExit(0 if result.wasSuccessful() else 1)
