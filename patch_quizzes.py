with open("src/canvas_mcp/tools/quizzes.py", "r") as f:
    content = f.read()

replacement = """        if engine.lower() == "classic":
            stats = await fetch_all_paginated_results(f"/courses/{course_id}/quizzes/{quiz_id_str}/statistics", {"per_page": 100})
            if isinstance(stats, dict) and "error" in stats:
                return f"Error fetching Classic Quiz statistics: {stats['error']}"
            
            if not stats:
                return f"No statistics found for Classic Quiz {quiz_id_str}."
                
            output = [f"Statistics for Classic Quiz {quiz_id_str}:"]
            for stat in stats:
                sub_stats = stat.get("submission_statistics", {})
                output.append(f"Score Average: {sub_stats.get('score_average', 'N/A')}")
                output.append(f"Score High: {sub_stats.get('score_high', 'N/A')}")
                output.append(f"Score Low: {sub_stats.get('score_low', 'N/A')}")
                output.append(f"Score Standard Deviation: {sub_stats.get('score_stdev', 'N/A')}")
                output.append(f"User Count: {sub_stats.get('user_count', 'N/A')}")
            return "\\n".join(output)
        
        else:
            from .assignments_analytics import get_assignment_analytics_impl
            return await get_assignment_analytics_impl(course_id, quiz_id_str)
"""

content = content.replace("""        if engine.lower() == "classic":
            stats = await fetch_all_paginated_results(f"/courses/{course_id}/quizzes/{quiz_id_str}/statistics", {"per_page": 100})
            if isinstance(stats, dict) and "error" in stats:
                return f"Error fetching Classic Quiz statistics: {stats['error']}"
            
            if not stats:
                return f"No statistics found for Classic Quiz {quiz_id_str}."
                
            output = [f"Statistics for Classic Quiz {quiz_id_str}:"]
            for stat in stats:
                # stat has "question_statistics" and "submission_statistics"
                sub_stats = stat.get("submission_statistics", {})
                output.append(f"Score Average: {sub_stats.get('score_average', 'N/A')}")
                output.append(f"Score High: {sub_stats.get('score_high', 'N/A')}")
                output.append(f"Score Low: {sub_stats.get('score_low', 'N/A')}")
                output.append(f"Score Standard Deviation: {sub_stats.get('score_stdev', 'N/A')}")
                output.append(f"User Count: {sub_stats.get('user_count', 'N/A')}")
            return "\\n".join(output)
        
        else:
            # New Quizzes - Reuse assignment analytics
            # We can literally just duplicate the get_assignment_analytics logic or call the underlying function
            # Since get_assignment_analytics is a bound tool, we can extract its `__wrapped__` but it's easier
            # to just copy the relevant parts or import it. Wait! Let's import it.
            from .assignments import get_assignment_analytics
            # The tool decorator is applied, but the function still works as async def if we bypass or if we just call it.
            # FastMCP decorators usually preserve the async callable. Let's try calling it directly.
            # But wait, get_assignment_analytics might be wrapped.
            # Actually, I can just call get_assignment_analytics.func if it is wrapped, or it might just be the same function.
            # But it's safer to implement the logic for New Quizzes manually or extract a helper in assignments.py.
            pass""", replacement)

with open("src/canvas_mcp/tools/quizzes.py", "w") as f:
    f.write(content)
