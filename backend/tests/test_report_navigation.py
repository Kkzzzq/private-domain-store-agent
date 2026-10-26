from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.quality.browser_extra import first_report_row


@pytest.mark.parametrize("expanded", [False, True])
def test_report_navigation_expands_hour_before_waiting_for_row(expanded):
    events = []
    summary = Mock()
    summary.click.side_effect = lambda: events.append("expand")
    row = Mock()
    row.wait_for.side_effect = lambda **kwargs: events.append("visible")
    group = Mock()
    group.get_attribute.return_value = "" if expanded else None
    group.locator.side_effect = lambda selector: SimpleNamespace(first=summary if selector == "summary" else row)
    page = Mock()
    page.locator.return_value = SimpleNamespace(first=group)

    assert first_report_row(page) is row
    page.locator.assert_called_once_with("details.qa-hour-report")
    group.wait_for.assert_called_once_with(state="attached")
    row.wait_for.assert_called_once_with(state="visible")
    assert events == (["visible"] if expanded else ["expand", "visible"])
