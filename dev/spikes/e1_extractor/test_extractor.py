import pytest
from pathlib import Path
from extractor import extract_prowess, extract_encounter

def test_extract_prowess_from_living():
    mock_gamestate = "\nliving={\n\t1234={\n\t\tfirst_name=\"Test\"\n\t\tskill={ 5 10 3 4 8 20 }\n\t}\n\t5678={\n\t\tfirst_name=\"NoSkill\"\n\t}\n}"
    assert extract_prowess(mock_gamestate, "1234") == 20
    assert extract_prowess(mock_gamestate, "5678") == 0
    assert extract_prowess(mock_gamestate, "9999") == 0

def test_extract_prowess_from_dead():
    mock_gamestate = "\ndead_unprunable={\n\t4321={\n\t\tfirst_name=\"Dead\"\n\t\tskill={ 0 0 0 0 0 15 }\n\t}\n}"
    assert extract_prowess(mock_gamestate, "4321") == 15

def test_extract_prowess_invalid_skill_block():
    mock_gamestate = "\nliving={\n\t999={\n\t\tfirst_name=\"Short\"\n\t\tskill={ 1 2 }\n\t}\n}"
    # If the skill block has fewer than 6 items, default to 0
    assert extract_prowess(mock_gamestate, "999") == 0

def test_extract_encounter_does_not_call_combat_participants_knights(tmp_path):
    save = tmp_path / "battle.ck3"
    save.write_text('''meta_data={ ironman=no }
living={
 10={ skill={ 0 0 0 0 0 12 } }
 11={ skill={ 0 0 0 0 0 9 } }
 12={ skill={ 0 0 0 0 0 7 } }
 20={ skill={ 0 0 0 0 0 8 } }
}
armies={ regiments={ } army_regiments={ } armies={ } }
combats={
 combat_results={ 42=none }
 combats={
  42={
   attacker={
    armies={ 100 }
    commander=10
    leader=11
    initial_men=500
    total_fighting_men=450
    character={ character=11 }
    character={ character=12 }
   }
   defender={
    armies={ 200 }
    commander=20
    initial_men=400
    total_fighting_men=350
   }
   phase=main
  }
 }
}
''', encoding='utf-8')

    manifest = extract_encounter(save, None, '42')
    sources = manifest['sides'][0]['prowess']
    assert [(source['id'], source['role']) for source in sources] == [
        ('10', 'commander'),
        ('11', 'leader'),
        ('12', 'combat_participant_unclassified'),
    ]
