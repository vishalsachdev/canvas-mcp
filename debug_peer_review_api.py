#!/usr/bin/env python3
"""
Debug script to understand Canvas API peer review comment structure.
"""

import asyncio
import sys
import os
import json

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from canvas_mcp.core.client import make_canvas_request
from canvas_mcp.core.cache import get_course_id


async def debug_peer_review_api():
    """Debug the Canvas API to understand peer review comment structure."""

    print("🔍 Debugging Canvas API Peer Review Comment Structure")
    print("=" * 60)

    course_identifier = "60366"
    assignment_id = "1368809"

    try:
        course_id = await get_course_id(course_identifier)

        print(f"Course ID: {course_id}")
        print(f"Assignment ID: {assignment_id}")
        print()

        # Test 1: Get peer reviews with different include parameters
        print("1. Testing peer reviews with various include parameters...")

        # Basic peer reviews
        print("\n   a) Basic peer reviews:")
        basic_response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id}/peer_reviews"
        )

        if "error" in basic_response:
            print(f"   ❌ Error: {basic_response['error']}")
        else:
            print(f"   ✅ Got {len(basic_response)} peer reviews")
            if basic_response:
                print(f"   Sample keys: {list(basic_response[0].keys())}")
                print(f"   Sample review: {json.dumps(basic_response[0], indent=4)}")

        # With submission_comment include
        print("\n   b) Peer reviews with submission_comment include:")
        comment_response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id}/peer_reviews",
            params={"include[]": ["submission_comment"]}
        )

        if "error" in comment_response:
            print(f"   ❌ Error: {comment_response['error']}")
        else:
            print(f"   ✅ Got {len(comment_response)} peer reviews")
            if comment_response:
                sample = comment_response[0]
                print(f"   Sample keys: {list(sample.keys())}")
                print(f"   Has submission_comment: {'submission_comment' in sample}")
                if 'submission_comment' in sample:
                    print(f"   Submission comment: {sample['submission_comment']}")

        # With all includes
        print("\n   c) Peer reviews with all includes:")
        all_response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id}/peer_reviews",
            params={"include[]": ["submission_comment", "user", "assessor"]}
        )

        if "error" in all_response:
            print(f"   ❌ Error: {all_response['error']}")
        else:
            print(f"   ✅ Got {len(all_response)} peer reviews")
            if all_response:
                sample = all_response[0]
                print(f"   Sample keys: {list(sample.keys())}")
                print(f"   Full sample: {json.dumps(sample, indent=4)}")

        # Test 2: Get submissions to see if comments are there
        print("\n2. Testing submissions endpoint for comments...")

        submissions_response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id}/submissions",
            params={"include[]": ["submission_comments"], "per_page": 5}
        )

        if "error" in submissions_response:
            print(f"   ❌ Error: {submissions_response['error']}")
        else:
            print(f"   ✅ Got {len(submissions_response)} submissions")
            for i, sub in enumerate(submissions_response[:2]):
                print(f"   Submission {i+1}:")
                print(f"     User ID: {sub.get('user_id')}")
                print(f"     Has submission_comments: {'submission_comments' in sub}")
                if 'submission_comments' in sub:
                    comments = sub['submission_comments']
                    print(f"     Number of comments: {len(comments)}")
                    if comments:
                        print(f"     Sample comment: {json.dumps(comments[0], indent=6)}")

        # Test 3: Try to get comments for a specific submission
        print("\n3. Testing specific submission comments...")

        if all_response and len(all_response) > 0:
            sample_review = all_response[0]
            user_id = sample_review.get('user_id')  # The reviewee

            if user_id:
                print(f"   Getting comments for user {user_id}...")
                user_submission_response = await make_canvas_request(
                    "get",
                    f"/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}",
                    params={"include[]": ["submission_comments"]}
                )

                if "error" in user_submission_response:
                    print(f"   ❌ Error: {user_submission_response['error']}")
                else:
                    print(f"   ✅ Got submission for user {user_id}")
                    if 'submission_comments' in user_submission_response:
                        comments = user_submission_response['submission_comments']
                        print(f"   Number of comments: {len(comments)}")
                        for i, comment in enumerate(comments[:3]):
                            print(f"   Comment {i+1}: {json.dumps(comment, indent=6)}")

        # Test 4: Check assignment details
        print("\n4. Checking assignment details...")
        assignment_response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id}"
        )

        if "error" in assignment_response:
            print(f"   ❌ Error: {assignment_response['error']}")
        else:
            print(f"   ✅ Assignment details:")
            print(f"     Name: {assignment_response.get('name')}")
            print(f"     Peer reviews enabled: {assignment_response.get('peer_reviews')}")
            print(f"     Has rubric: {'rubric' in assignment_response}")
            if 'rubric' in assignment_response:
                print(f"     Rubric criteria: {len(assignment_response['rubric'])}")

    except Exception as e:
        print(f"❌ Debug failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_peer_review_api())