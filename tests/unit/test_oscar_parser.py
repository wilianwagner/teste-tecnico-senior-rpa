from collections.abc import Callable

import pytest

from app.core.exceptions import CrawlerError
from app.crawlers.oscar.parser import parse_films


class TestParseFilms:
    def test_parses_all_rows(self, load_fixture: Callable[[str], str]) -> None:
        films = parse_films(load_fixture("oscar_2015_rendered.html"), year=2015)

        assert len(films) == 4
        assert all(film.year == 2015 for film in films)

    def test_strips_whitespace_from_titles(self, load_fixture: Callable[[str], str]) -> None:
        films = parse_films(load_fixture("oscar_2015_rendered.html"), year=2015)

        assert [film.title for film in films] == [
            "Spotlight",
            "Mad Max: Fury Road",
            "The Revenant",
            "Bridge of Spies",
        ]

    def test_parses_numeric_fields(self, load_fixture: Callable[[str], str]) -> None:
        spotlight = parse_films(load_fixture("oscar_2015_rendered.html"), year=2015)[0]

        assert spotlight.nominations == 6
        assert spotlight.awards == 2

    def test_best_picture_flag_only_on_winner(self, load_fixture: Callable[[str], str]) -> None:
        films = parse_films(load_fixture("oscar_2015_rendered.html"), year=2015)

        assert [film.best_picture for film in films] == [True, False, False, False]

    def test_page_without_film_rows_returns_empty_list(self) -> None:
        assert parse_films("<html><body></body></html>", year=2010) == []

    def test_missing_cell_raises_crawler_error(self) -> None:
        html = "<table><tr class='film'><td class='film-title'>Movie</td></tr></table>"

        with pytest.raises(CrawlerError, match="Malformed oscar film row"):
            parse_films(html, year=2010)
