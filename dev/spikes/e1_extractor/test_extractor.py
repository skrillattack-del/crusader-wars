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
