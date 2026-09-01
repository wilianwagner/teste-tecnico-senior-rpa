from pydantic import BaseModel, ConfigDict


class HockeyTeamData(BaseModel):
    model_config = ConfigDict(frozen=True)

    team_name: str
    year: int
    wins: int
    losses: int
    ot_losses: int | None = None
    win_pct: float
    goals_for: int
    goals_against: int
    goal_diff: int


class OscarFilmData(BaseModel):
    model_config = ConfigDict(frozen=True)

    year: int
    title: str
    nominations: int
    awards: int
    best_picture: bool = False
