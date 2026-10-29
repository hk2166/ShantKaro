from pathlib import Path

import pytest
import yaml

from shant.scenarios.loader import SCENARIOS_DIR, ScenarioError, load_all, load_scenario
from shant.tags import AGGRAVATING, CALMING, Tag


def test_every_tag_is_either_calming_or_aggravating() -> None:
    assert CALMING | AGGRAVATING == set(Tag)
    assert not CALMING & AGGRAVATING


@pytest.mark.parametrize("path", sorted(SCENARIOS_DIR.glob("*.yaml")), ids=lambda p: p.stem)
def test_every_scenario_file_validates(path: Path) -> None:
    assert load_scenario(path).id == path.stem


def test_the_three_v1_scenarios_exist() -> None:
    assert set(load_all()) == {"sharma_uncle", "lakshmi_aunty", "rohan"}


def test_band_for_picks_the_first_band_that_covers_the_anger() -> None:
    voice = load_all()["sharma_uncle"].voice
    assert voice.band_for(0).up_to == 30
    assert voice.band_for(30).up_to == 30
    assert voice.band_for(31).up_to == 60
    assert voice.band_for(100).up_to == 100


@pytest.fixture
def sharma() -> dict:
    return yaml.safe_load((SCENARIOS_DIR / "sharma_uncle.yaml").read_text(encoding="utf-8"))


def write(tmp_path: Path, data: dict, name: str = "sharma_uncle") -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_missing_section_names_the_file_and_the_field(tmp_path: Path, sharma: dict) -> None:
    del sharma["policy"]
    with pytest.raises(ScenarioError, match=r"(?s)sharma_uncle\.yaml.*policy"):
        load_scenario(write(tmp_path, sharma))


def test_misspelt_key_is_rejected(tmp_path: Path, sharma: dict) -> None:
    sharma["opening_line"] = sharma.pop("opening_lines")
    with pytest.raises(ScenarioError, match="opening_line"):
        load_scenario(write(tmp_path, sharma))


def test_unknown_tag_is_rejected(tmp_path: Path, sharma: dict) -> None:
    sharma["dynamics"]["tag_weights"]["smiled"] = -5
    with pytest.raises(ScenarioError, match="smiled"):
        load_scenario(write(tmp_path, sharma))


def test_calming_tag_cannot_raise_anger(tmp_path: Path, sharma: dict) -> None:
    sharma["dynamics"]["tag_weights"]["apologised"] = 5
    with pytest.raises(ScenarioError, match="apologised calms the customer"):
        load_scenario(write(tmp_path, sharma))


def test_bands_must_end_at_100(tmp_path: Path, sharma: dict) -> None:
    sharma["voice"]["bands"] = sharma["voice"]["bands"][:-1]
    with pytest.raises(ScenarioError, match="up_to: 100"):
        load_scenario(write(tmp_path, sharma))


def test_win_threshold_must_be_below_starting_anger(tmp_path: Path, sharma: dict) -> None:
    sharma["dynamics"]["win_at_or_below"] = 80
    with pytest.raises(ScenarioError, match="below starting_anger"):
        load_scenario(write(tmp_path, sharma))


def test_id_must_match_file_name(tmp_path: Path, sharma: dict) -> None:
    with pytest.raises(ScenarioError, match="must match the file name"):
        load_scenario(write(tmp_path, sharma, name="someone_else"))


def test_invalid_yaml_is_reported_with_the_file_name(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("persona: [unclosed", encoding="utf-8")
    with pytest.raises(ScenarioError, match=r"broken\.yaml"):
        load_scenario(path)


def test_empty_folder_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="no scenario files"):
        load_all(tmp_path)


def test_bands_must_be_in_increasing_order(tmp_path: Path, sharma: dict) -> None:
    sharma["voice"]["bands"] = list(reversed(sharma["voice"]["bands"]))
    with pytest.raises(ScenarioError, match="increasing order"):
        load_scenario(write(tmp_path, sharma))


def test_aggravating_tag_cannot_calm_the_customer(tmp_path: Path, sharma: dict) -> None:
    sharma["dynamics"]["tag_weights"]["dismissive"] = -5
    with pytest.raises(ScenarioError, match="dismissive angers the customer"):
        load_scenario(write(tmp_path, sharma))


def test_every_ending_needs_a_closing_line(tmp_path: Path, sharma: dict) -> None:
    sharma["closing_lines"]["timed_out"] = []
    with pytest.raises(ScenarioError, match="timed_out"):
        load_scenario(write(tmp_path, sharma))


def test_the_trainee_may_speak_their_own_language_or_the_customers() -> None:
    scenarios = load_all()
    assert scenarios["sharma_uncle"].trainee_languages == ["en-IN", "hi-IN"]
    assert scenarios["lakshmi_aunty"].trainee_languages == ["en-IN", "ta-IN"]
    assert scenarios["rohan"].trainee_languages == ["en-IN"]
