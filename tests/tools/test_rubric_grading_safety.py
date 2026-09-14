"""Regressions for #374: no writes after failed checks or false success."""
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client, FastMCP

from canvas_mcp.tools.assignments import register_educator_assignment_tools
from canvas_mcp.tools.rubrics import register_rubric_tools


async def call_grade(bulk, assignment, response):
    module = 'assignments' if bulk else 'rubrics'
    mcp = FastMCP('test')
    (register_educator_assignment_tools if bulk else register_rubric_tools)(mcp)
    with patch(f'canvas_mcp.tools.{module}.make_canvas_request', new_callable=AsyncMock) as req, \
         patch(f'canvas_mcp.tools.{module}.get_course_id', new_callable=AsyncMock, return_value='1'), \
         patch(f'canvas_mcp.tools.{module}.get_course_code', new_callable=AsyncMock, return_value='TEST'):
        req.side_effect = lambda method, *a, **kw: assignment if method == 'get' else response
        args = {'course_identifier': '1', 'assignment_id': '2'}
        assessment = {'a': {'points': 5}, 'b': {'points': 9}}
        if bulk:
            args['grades'] = {'3': {'rubric_assessment': assessment, 'grade': 99}}
        else:
            args.update(user_id='3', rubric_assessment=assessment)
        async with Client(mcp) as client:
            result = await client.call_tool_mcp('bulk_grade_submissions' if bulk else 'grade_with_rubric', args)
        return result.content[0].text, req.call_args_list


@pytest.mark.asyncio
@pytest.mark.parametrize('bulk', [False, True])
@pytest.mark.parametrize('assignment', [{'error': 'lookup failed'}, {}, {'use_rubric_for_grading': False}])
async def test_precheck_failure_never_writes(bulk, assignment):
    text, calls = await call_grade(bulk, assignment, {'score': 14, 'grade': '14'})
    assert not any(c.args[0] == 'put' for c in calls)
    assert 'error' in text.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize('bulk', [False, True])
@pytest.mark.parametrize('score', [None, 99, 5])
async def test_grade_outcome_uses_canvas_score_and_ignored_criteria(bulk, score):
    assignment = {'use_rubric_for_grading': True, 'rubric': [
        {'id': 'a'}, {'id': 'b', 'ignore_for_scoring': True}]}
    text, calls = await call_grade(bulk, assignment, {'score': score, 'grade': str(score)})
    writes = [c for c in calls if c.args[0] == 'put']
    assert len(writes) == 1
    assert 'submission[posted_grade]' not in writes[0].kwargs['data']
    if score == 5:
        assert 'unconfirmed' not in text.lower()
        assert ('Graded:  1' if bulk else 'Successfully') in text
    else:
        assert 'unconfirmed' in text.lower()
        if bulk:
            assert 'Graded:  0' in text
        else:
            assert 'Successfully' not in text


@pytest.mark.parametrize('score', [0, 5])
def test_confirmation_requires_complete_metadata_and_accepts_zero(score):
    from canvas_mcp.tools.rubrics import rubric_grade_is_confirmed

    assessment = {'a': {'points': score}}
    response = {'score': score, 'grade': str(score)}
    assert rubric_grade_is_confirmed({'rubric': [{'id': 'a'}]}, assessment, response)
    assert not rubric_grade_is_confirmed({}, assessment, response)
    assert not rubric_grade_is_confirmed({'rubric': [{'id': 'a'}, {'id': 'b'}]}, assessment, response)
    assert not rubric_grade_is_confirmed({'rubric': [{'id': 'a'}]}, assessment, {'score': score})
