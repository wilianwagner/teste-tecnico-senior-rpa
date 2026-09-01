from collections.abc import Callable

import pytest

from app.core.exceptions import CrawlerError
from app.crawlers.hockey.parser import parse_teams, parse_total_pages


class TestParseTeams:
    def test_parses_all_rows_from_real_page(self, load_fixture: Callable[[str], str]) -> None:
        teams = parse_teams(load_fixture("hockey_page1.html"))

        assert len(teams) == 25

    def test_parses_first_row_fields(self, load_fixture: Callable[[str], str]) -> None:
        first = parse_teams(load_fixture("hockey_page1.html"))[0]

        assert first.team_name == "Boston Bruins"
        assert first.year == 1990
        assert first.wins == 44
        assert first.losses == 24
        assert first.win_pct == 0.55
        assert first.goals_for == 299
        assert first.goals_against == 264
        assert first.goal_diff == 35

    def test_empty_ot_losses_becomes_none(self, load_fixture: Callable[[str], str]) -> None:
        first = parse_teams(load_fixture("hockey_page1.html"))[0]

        assert first.ot_losses is None

    def test_parses_negative_goal_diff_and_filled_ot_losses(
        self, load_fixture: Callable[[str], str]
    ) -> None:
        teams = parse_teams(load_fixture("hockey_single_page.html"))

        assert len(teams) == 1
        team = teams[0]
        assert team.team_name == "Anaheim Ducks"
        assert team.ot_losses == 12
        assert team.win_pct == 0.415
        assert team.goal_diff == -27

    def test_page_without_team_rows_returns_empty_list(self) -> None:
        assert parse_teams("<html><body><p>no table</p></body></html>") == []

    def test_missing_cell_raises_crawler_error(self) -> None:
        html = """
        <table>
            <tr class="team">
                <td class="name">Broken Team</td>
                <td class="year">1990</td>
            </tr>
        </table>
        """

        with pytest.raises(CrawlerError, match="Missing cell"):
            parse_teams(html)

    def test_non_numeric_cell_raises_crawler_error(self) -> None:
        html = """
        <table>
            <tr class="team">
                <td class="name">Broken Team</td>
                <td class="year">not-a-year</td>
                <td class="wins">1</td>
                <td class="losses">2</td>
                <td class="ot-losses"></td>
                <td class="pct">0.5</td>
                <td class="gf">10</td>
                <td class="ga">20</td>
                <td class="diff">-10</td>
            </tr>
        </table>
        """

        with pytest.raises(CrawlerError, match="Malformed hockey team row"):
            parse_teams(html)


class TestParseTotalPages:
    def test_reads_last_page_from_pagination(self, load_fixture: Callable[[str], str]) -> None:
        assert parse_total_pages(load_fixture("hockey_page1.html")) == 24

    def test_page_without_pagination_defaults_to_one(
        self, load_fixture: Callable[[str], str]
    ) -> None:
        assert parse_total_pages(load_fixture("hockey_single_page.html")) == 1
