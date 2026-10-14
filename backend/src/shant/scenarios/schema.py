"""Scenario files: who the customer is, what went wrong, and what the agent may offer."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shant.tags import AGGRAVATING, CALMING, Tag

LANGUAGE_CODE = r"^[a-z]{2}-(IN|en)$"


class Strict(BaseModel):
    # Unknown keys are errors, so a typo in a YAML file fails loudly instead of being ignored.
    model_config = ConfigDict(extra="forbid", frozen=True)


class Company(Strict):
    name: str
    industry: str


class Persona(Strict):
    name: str
    age: int = Field(ge=18, le=100)
    city: str
    background: str
    speaking_style: str


class Grievance(Strict):
    summary: str = Field(max_length=120)
    facts: list[str] = Field(min_length=1)


class Policy(Strict):
    allowed_remedies: list[str] = Field(min_length=1)
    forbidden_promises: list[str] = Field(min_length=1)


class AngerBand(Strict):
    up_to: int = Field(ge=0, le=100)
    tts_speed: float = Field(ge=0.85, le=1.15)
    style: str


class Voice(Strict):
    tts_voice: str
    tts_language: str = Field(pattern=LANGUAGE_CODE)
    stt_language: str = Field(pattern=LANGUAGE_CODE)
    bands: list[AngerBand] = Field(min_length=1)

    @model_validator(mode="after")
    def bands_cover_0_to_100(self) -> Self:
        limits = [band.up_to for band in self.bands]
        if limits != sorted(set(limits)):
            raise ValueError("bands must be listed in increasing order of up_to, without repeats")
        if limits[-1] != 100:
            raise ValueError("the last band must have up_to: 100")
        return self

    def band_for(self, anger: int) -> AngerBand:
        return next(band for band in self.bands if anger <= band.up_to)


class LanguageSwitch(Strict):
    at_anger: int = Field(ge=1, le=99)
    language: str = Field(pattern=LANGUAGE_CODE)


class Dynamics(Strict):
    starting_anger: int = Field(ge=1, le=99)
    win_at_or_below: int = Field(default=20, ge=0, le=98)
    max_strikes: int = Field(default=3, ge=1)
    time_limit_s: int = Field(default=180, ge=30, le=900)
    tag_weights: dict[Tag, int]
    language_switch: LanguageSwitch | None = None

    @model_validator(mode="after")
    def weights_and_thresholds_make_sense(self) -> Self:
        for tag, weight in self.tag_weights.items():
            if tag in CALMING and weight > 0:
                raise ValueError(f"{tag} calms the customer, so its weight must be 0 or less")
            if tag in AGGRAVATING and weight < 0:
                raise ValueError(f"{tag} angers the customer, so its weight must be 0 or more")
        if self.win_at_or_below >= self.starting_anger:
            raise ValueError("win_at_or_below must be below starting_anger")
        return self


class Scenario(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    title: str
    company: Company
    persona: Persona
    grievance: Grievance
    policy: Policy
    voice: Voice
    dynamics: Dynamics
    opening_lines: list[str] = Field(min_length=1)
