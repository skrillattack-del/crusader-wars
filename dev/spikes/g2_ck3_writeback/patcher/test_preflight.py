import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import preflight as p

FIXTURE = '''meta_data={
 ironman=no
}
armies={
 regiments={ 1={ current=500 } }
 army_regiments={ 2={ cached={ current=500 } } }
 armies={ 10={ regiments={ 2 } } }
}
combats={
 combat_results={ 8=none }
 combats={
  42={
   attacker={
    armies={ 10 }
    initial_men=500
    total_fighting_men=450.5
   }
   defender={
    armies={ 20 }
    initial_men=400
    total_fighting_men=350.25
   }
   phase=main
  }
 }
}
'''

class PreflightTests(unittest.TestCase):
    def test_direct_blocks_ignore_nested_names_comments_and_strings(self):
        body = '{ nested={ armies={ 99 } } # armies={ 88 }\n label="armies={ 77 }" armies={ 10 } }'
        self.assertEqual(p.unique(body, 'armies'), '{ 10 }')
        self.assertEqual(p.inventory(FIXTURE)[0]['combats'][0]['combat_id'], '42')

    def test_archive_copy_plan_and_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/'source.ck3'; out=root/'run'
            with zipfile.ZipFile(source, 'w') as z: z.writestr('gamestate', FIXTURE)
            original=source.read_bytes()
            p.intake(source,out)
            self.assertEqual((out/'before.ck3').read_bytes(), original)
            result=p.plan(out,'42')
            self.assertEqual(result['sides']['defender']['synthetic_casualties'],75)
            self.assertEqual(source.read_bytes(),original)
            with self.assertRaises(FileExistsError): p.plan(out,'42')
            with self.assertRaises(ValueError): p.plan(out,'999')
            (out/'before.ck3').write_bytes(b'changed')
            with self.assertRaises(ValueError): p.plan(out,'42')

    def test_binary_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'binary.ck3'; path.write_bytes(b'\x00binary')
            with self.assertRaises(ValueError): p.read_gamestate(path)

if __name__=='__main__': unittest.main()
