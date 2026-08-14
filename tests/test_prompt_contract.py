from app.agent.prompt import SYSTEM_PROMPT
from app.tools.definitions import SEARCH_MENU_TOOL, SELECT_SEARCH_RESULT_TOOL


def test_prompt_enforces_agent_backend_boundary_and_direct_search() -> None:
    assert "FastAPI owns workflow state" in SYSTEM_PROMPT
    assert "Spring Boot owns authentication" in SYSTEM_PROMPT
    assert "call\n  search_menu immediately" in SYSTEM_PROMPT
    assert "last_search_results" in SYSTEM_PROMPT
    assert "Never offer to add an item to a cart" in SYSTEM_PROMPT


def test_tool_description_defines_refinement_semantics() -> None:
    description = SEARCH_MENU_TOOL["description"]
    assert "start_new_search=false" in description
    assert "FastAPI will merge" in description


def test_selection_tool_is_state_only() -> None:
    description = SELECT_SEARCH_RESULT_TOOL["description"]
    assert "selected_item" in description
    assert "does not add anything to a cart" in description
