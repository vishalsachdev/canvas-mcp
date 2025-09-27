"""
Canvas Peer Review Comments Analysis Module

Provides comprehensive peer review comment extraction, analysis, and reporting
capabilities for Canvas assignments.
"""

import statistics
from collections import Counter
from typing import Any

from .anonymization import generate_anonymous_id
from .client import fetch_all_paginated_results, make_canvas_request
from .dates import format_date


class PeerReviewCommentAnalyzer:
    """Handles peer review comment extraction and analysis for Canvas assignments."""

    def __init__(self) -> None:
        self.quality_keywords = {
            'constructive': [
                'suggest', 'recommend', 'consider', 'improve', 'enhance', 'modify',
                'try', 'could', 'might', 'perhaps', 'instead', 'alternative'
            ],
            'specific': [
                'line', 'section', 'paragraph', 'function', 'method', 'variable',
                'code', 'syntax', 'logic', 'algorithm', 'implementation'
            ],
            'generic': [
                'good job', 'nice work', 'well done', 'great', 'awesome', 'perfect',
                'looks good', 'fine', 'ok', 'okay', 'correct'
            ],
            'harsh': [
                'terrible', 'awful', 'wrong', 'bad', 'horrible', 'stupid',
                'useless', 'worthless', 'garbage', 'trash'
            ]
        }

    async def get_peer_review_comments(
        self,
        course_id: int,
        assignment_id: int,
        include_reviewer_info: bool = True,
        include_reviewee_info: bool = True,
        include_submission_context: bool = False,
        anonymize_students: bool = False
    ) -> dict[str, Any]:
        """
        Retrieve actual comment text for peer reviews on a specific assignment.

        Args:
            course_id: Canvas course ID
            assignment_id: Canvas assignment ID
            include_reviewer_info: Include reviewer student information
            include_reviewee_info: Include reviewee student information
            include_submission_context: Include original submission details
            anonymize_students: Replace student names with anonymous IDs

        Returns:
            Dict containing assignment info, peer reviews with comments, and summary statistics
        """
        try:
            # Get assignment details
            assignment_response = await make_canvas_request(
                "get",
                f"/courses/{course_id}/assignments/{assignment_id}"
            )

            if "error" in assignment_response:
                return {"error": f"Failed to get assignment: {assignment_response['error']}"}

            # Get peer reviews (these don't include comments directly)
            peer_reviews_response = await make_canvas_request(
                "get",
                f"/courses/{course_id}/assignments/{assignment_id}/peer_reviews",
                params={"include[]": ["user", "assessor"]}
            )

            if "error" in peer_reviews_response:
                return {"error": f"Failed to get peer reviews: {peer_reviews_response['error']}"}

            peer_reviews: list[Any] = peer_reviews_response if isinstance(peer_reviews_response, list) else []

            # Get users for name mapping if needed
            users_map = {}
            if include_reviewer_info or include_reviewee_info:
                users_response = await fetch_all_paginated_results(
                    f"/courses/{course_id}/users",
                    {"enrollment_type[]": "student", "per_page": 100}
                )
                if isinstance(users_response, list):
                    users_map = {user["id"]: user for user in users_response}

            # Get ALL submissions with comments (needed to extract peer review comments)
            submissions_map = {}
            submissions_by_id = {}
            submissions_response = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments/{assignment_id}/submissions",
                {"include[]": ["submission_comments"], "per_page": 100}
            )
            if isinstance(submissions_response, list):
                for sub in submissions_response:
                    submissions_map[sub["user_id"]] = sub
                    submissions_by_id[sub["id"]] = sub

            # Process peer review comments
            processed_reviews = []
            total_comments = 0
            comments_with_text = 0
            empty_comments = 0
            total_word_count = 0

            for pr in peer_reviews:
                reviewer_id = pr.get("assessor_id")
                reviewee_id = pr.get("user_id")

                if not reviewer_id or not reviewee_id:
                    continue

                # Build reviewer info
                reviewer_info = {"student_id": reviewer_id}
                if include_reviewer_info and reviewer_id in users_map:
                    user = users_map[reviewer_id]
                    if anonymize_students:
                        reviewer_info.update({
                            "student_name": generate_anonymous_id(reviewer_id, "Student"),
                            "anonymous_id": generate_anonymous_id(reviewer_id, "Reviewer")
                        })
                    else:
                        reviewer_info.update({
                            "student_name": user.get("name", "Unknown"),
                            "anonymous_id": generate_anonymous_id(reviewer_id, "Reviewer")
                        })

                # Build reviewee info
                reviewee_info = {"student_id": reviewee_id}
                if include_reviewee_info and reviewee_id in users_map:
                    user = users_map[reviewee_id]
                    if anonymize_students:
                        reviewee_info.update({
                            "student_name": generate_anonymous_id(reviewee_id, "Student"),
                            "anonymous_id": generate_anonymous_id(reviewee_id, "Reviewee")
                        })
                    else:
                        reviewee_info.update({
                            "student_name": user.get("name", "Unknown"),
                            "anonymous_id": generate_anonymous_id(reviewee_id, "Reviewee")
                        })

                # Build submission info
                submission_info = {}
                if include_submission_context and reviewee_id in submissions_map:
                    sub = submissions_map[reviewee_id]
                    submission_info = {
                        "submission_id": sub.get("id"),
                        "submitted_at": format_date(sub.get("submitted_at")),
                        "attempt": sub.get("attempt", 1)
                    }

                # Process comment content - Extract from submission comments
                review_content: dict[str, Any] = {
                    "comment_text": "",
                    "rating": None,
                    "rubric_assessments": [],
                    "timestamp": None,
                    "word_count": 0,
                    "character_count": 0
                }

                # Get the submission that was reviewed
                asset_id = pr.get("asset_id")  # This is the submission ID
                if asset_id and asset_id in submissions_by_id:
                    submission = submissions_by_id[asset_id]
                    submission_comments = submission.get("submission_comments", [])

                    # Find comments from this specific reviewer
                    for comment in submission_comments:
                        if comment.get("author_id") == reviewer_id:
                            comment_text = comment.get("comment", "")
                            review_content.update({
                                "comment_text": comment_text,
                                "timestamp": format_date(comment.get("created_at")),
                                "word_count": len(comment_text.split()) if comment_text else 0,
                                "character_count": len(comment_text) if comment_text else 0
                            })

                            total_word_count += review_content["word_count"]
                            if comment_text.strip():
                                comments_with_text += 1
                            else:
                                empty_comments += 1
                            break  # Use the first comment from this reviewer
                    else:
                        # No comment found from this reviewer
                        empty_comments += 1
                else:
                    # No submission found for this asset_id
                    empty_comments += 1

                # Try to extract rating from rubric assessments if available
                # Note: This would require additional API calls to get rubric assessments
                # For now, we'll leave this as placeholder

                total_comments += 1

                review_data = {
                    "review_id": f"review_{pr.get('id', 'unknown')}",
                    "reviewer": reviewer_info,
                    "reviewee": reviewee_info,
                    "review_content": review_content
                }

                if include_submission_context:
                    review_data["submission_info"] = submission_info

                processed_reviews.append(review_data)

            # Calculate summary statistics
            avg_word_count = total_word_count / total_comments if total_comments > 0 else 0

            result = {
                "assignment_info": {
                    "assignment_id": assignment_id,
                    "assignment_name": assignment_response.get("name", "Unknown"),
                    "total_reviews": len(peer_reviews),
                    "completed_reviews": total_comments
                },
                "peer_reviews": processed_reviews,
                "summary_statistics": {
                    "total_comments": total_comments,
                    "average_word_count": round(avg_word_count, 1),
                    "comments_with_text": comments_with_text,
                    "empty_comments": empty_comments,
                    "average_rating": None  # Placeholder for future rubric integration
                }
            }

            return result

        except Exception as e:
            return {"error": f"Failed to get peer review comments: {str(e)}"}

    async def analyze_peer_review_quality(
        self,
        course_id: int,
        assignment_id: int,
        analysis_criteria: dict[str, Any] | None = None,
        generate_report: bool = True
    ) -> dict[str, Any]:
        """
        Analyze the quality and content of peer review comments.

        Args:
            course_id: Canvas course ID
            assignment_id: Canvas assignment ID
            analysis_criteria: Custom analysis criteria (optional)
            generate_report: Whether to generate detailed analysis report

        Returns:
            Dict containing comprehensive quality analysis
        """
        try:
            # First get all comments
            comments_data = await self.get_peer_review_comments(
                course_id, assignment_id, anonymize_students=True
            )

            if "error" in comments_data:
                return comments_data

            reviews = comments_data.get("peer_reviews", [])

            if not reviews:
                return {"error": "No peer reviews found for analysis"}

            # Extract comment texts for analysis
            comment_texts = []
            word_counts = []
            quality_scores = []
            flagged_reviews = []

            for review in reviews:
                content = review.get("review_content", {})
                comment_text = content.get("comment_text", "")
                word_count = content.get("word_count", 0)

                comment_texts.append(comment_text)
                word_counts.append(word_count)

                # Calculate quality score for this comment
                quality_score = self._calculate_quality_score(comment_text)
                quality_scores.append(quality_score)

                # Flag problematic reviews
                if quality_score < 2.0 or word_count < 5:
                    flagged_reviews.append({
                        "review_id": review.get("review_id"),
                        "flag_reason": "low_quality" if quality_score < 2.0 else "extremely_short",
                        "comment": comment_text[:100] + "..." if len(comment_text) > 100 else comment_text,
                        "word_count": word_count,
                        "quality_score": round(quality_score, 1)
                    })

            # Calculate statistics
            total_reviews = len(reviews)
            word_count_stats = self._calculate_word_count_stats(word_counts)
            constructiveness_analysis = self._analyze_constructiveness(comment_texts)
            sentiment_analysis = self._analyze_sentiment(comment_texts)

            # Quality distribution
            high_quality = sum(1 for score in quality_scores if score >= 4.0)
            medium_quality = sum(1 for score in quality_scores if 2.0 <= score < 4.0)
            low_quality = sum(1 for score in quality_scores if score < 2.0)

            avg_quality_score = statistics.mean(quality_scores) if quality_scores else 0

            # Generate recommendations
            recommendations = self._generate_recommendations(
                flagged_reviews, word_count_stats, constructiveness_analysis
            )

            result = {
                "overall_analysis": {
                    "total_reviews_analyzed": total_reviews,
                    "quality_distribution": {
                        "high_quality": high_quality,
                        "medium_quality": medium_quality,
                        "low_quality": low_quality
                    },
                    "average_quality_score": round(avg_quality_score, 1)
                },
                "detailed_metrics": {
                    "word_count_stats": word_count_stats,
                    "constructiveness_analysis": constructiveness_analysis,
                    "sentiment_analysis": sentiment_analysis
                },
                "flagged_reviews": flagged_reviews[:20],  # Limit to top 20
                "recommendations": recommendations
            }

            return result

        except Exception as e:
            return {"error": f"Failed to analyze peer review quality: {str(e)}"}

    def _calculate_quality_score(self, comment_text: str) -> float:
        """Calculate a quality score for a peer review comment."""
        if not comment_text or not comment_text.strip():
            return 0.0

        score = 2.0  # Base score
        text_lower = comment_text.lower()

        # Word count factor
        word_count = len(comment_text.split())
        if word_count >= 20:
            score += 1.0
        elif word_count >= 10:
            score += 0.5
        elif word_count < 5:
            score -= 1.0

        # Constructive language
        constructive_count = sum(1 for word in self.quality_keywords['constructive']
                                if word in text_lower)
        score += min(constructive_count * 0.3, 1.0)

        # Specific language
        specific_count = sum(1 for word in self.quality_keywords['specific']
                           if word in text_lower)
        score += min(specific_count * 0.2, 0.8)

        # Generic language penalty
        generic_count = sum(1 for phrase in self.quality_keywords['generic']
                          if phrase in text_lower)
        score -= min(generic_count * 0.4, 1.5)

        # Harsh language penalty
        harsh_count = sum(1 for word in self.quality_keywords['harsh']
                         if word in text_lower)
        score -= harsh_count * 0.5

        # Question marks indicate engagement
        if '?' in comment_text:
            score += 0.3

        return max(0.0, min(5.0, score))

    def _calculate_word_count_stats(self, word_counts: list[int]) -> dict[str, float]:
        """Calculate word count statistics."""
        if not word_counts:
            return {"mean": 0, "median": 0, "std_dev": 0, "min": 0, "max": 0}

        return {
            "mean": round(statistics.mean(word_counts), 1),
            "median": statistics.median(word_counts),
            "std_dev": round(statistics.stdev(word_counts), 1) if len(word_counts) > 1 else 0,
            "min": min(word_counts),
            "max": max(word_counts)
        }

    def _analyze_constructiveness(self, comment_texts: list[str]) -> dict[str, int]:
        """Analyze constructiveness of comments."""
        constructive_count = 0
        generic_count = 0
        specific_count = 0

        for text in comment_texts:
            text_lower = text.lower()

            # Check for constructive language
            if any(word in text_lower for word in self.quality_keywords['constructive']):
                constructive_count += 1

            # Check for generic language
            if any(phrase in text_lower for phrase in self.quality_keywords['generic']):
                generic_count += 1

            # Check for specific language
            if any(word in text_lower for word in self.quality_keywords['specific']):
                specific_count += 1

        return {
            "constructive_feedback_count": constructive_count,
            "generic_comments": generic_count,
            "specific_suggestions": specific_count
        }

    def _analyze_sentiment(self, comment_texts: list[str]) -> dict[str, float]:
        """Basic sentiment analysis of comments."""
        positive_words = ['good', 'great', 'excellent', 'nice', 'well', 'correct', 'clear']
        negative_words = ['bad', 'wrong', 'poor', 'unclear', 'confusing', 'incorrect']

        positive_count = 0
        negative_count = 0
        neutral_count = 0

        for text in comment_texts:
            text_lower = text.lower()
            pos_score = sum(1 for word in positive_words if word in text_lower)
            neg_score = sum(1 for word in negative_words if word in text_lower)

            if pos_score > neg_score:
                positive_count += 1
            elif neg_score > pos_score:
                negative_count += 1
            else:
                neutral_count += 1

        total = len(comment_texts)
        return {
            "positive_sentiment": round(positive_count / total, 2) if total > 0 else 0,
            "neutral_sentiment": round(neutral_count / total, 2) if total > 0 else 0,
            "negative_sentiment": round(negative_count / total, 2) if total > 0 else 0
        }

    def _generate_recommendations(
        self,
        flagged_reviews: list[dict],
        word_count_stats: dict,
        constructiveness_analysis: dict
    ) -> list[str]:
        """Generate recommendations based on analysis."""
        recommendations = []

        if len(flagged_reviews) > 0:
            recommendations.append(
                f"{len(flagged_reviews)} reviews flagged as low quality - may need instructor follow-up"
            )

        if word_count_stats.get("mean", 0) < 15:
            recommendations.append(
                "Average comment length is low - consider providing more specific feedback guidelines"
            )

        if constructiveness_analysis.get("generic_comments", 0) > constructiveness_analysis.get("constructive_feedback_count", 0):
            recommendations.append(
                "Many comments are generic - consider teaching specific feedback techniques"
            )

        if not recommendations:
            recommendations.append("Overall comment quality appears satisfactory")

        return recommendations

    async def identify_problematic_peer_reviews(
        self,
        course_id: int,
        assignment_id: int,
        criteria: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Flag reviews that may need instructor attention.

        Args:
            course_id: Canvas course ID
            assignment_id: Canvas assignment ID
            criteria: Custom flagging criteria (optional)

        Returns:
            Dict containing flagged reviews and reasons
        """
        try:
            # Default criteria
            default_criteria = {
                "min_word_count": 10,
                "generic_phrases": ["good job", "nice work", "looks good"],
                "max_quality_score": 2.0
            }

            if criteria:
                default_criteria.update(criteria)

            # Get comments for analysis
            comments_data = await self.get_peer_review_comments(
                course_id, assignment_id, anonymize_students=True
            )

            if "error" in comments_data:
                return comments_data

            reviews = comments_data.get("peer_reviews", [])
            flagged_reviews = []

            for review in reviews:
                content = review.get("review_content", {})
                comment_text = content.get("comment_text", "")
                word_count = content.get("word_count", 0)

                flags = []

                # Check word count
                if word_count < default_criteria["min_word_count"]:
                    flags.append("too_short")

                # Check for generic phrases
                text_lower = comment_text.lower()
                for phrase in default_criteria["generic_phrases"]:
                    if phrase in text_lower:
                        flags.append("generic_language")
                        break

                # Check quality score
                quality_score = self._calculate_quality_score(comment_text)
                if quality_score <= default_criteria["max_quality_score"]:
                    flags.append("low_quality")

                # Check for copy-paste patterns (identical comments)
                # This would require comparing against all other comments

                # Check for potentially inappropriate content
                if any(word in text_lower for word in self.quality_keywords['harsh']):
                    flags.append("potentially_harsh")

                if flags:
                    flagged_reviews.append({
                        "review_id": review.get("review_id"),
                        "reviewer_id": review.get("reviewer", {}).get("anonymous_id", "Unknown"),
                        "reviewee_id": review.get("reviewee", {}).get("anonymous_id", "Unknown"),
                        "flags": flags,
                        "comment_preview": comment_text[:100] + "..." if len(comment_text) > 100 else comment_text,
                        "word_count": word_count,
                        "quality_score": round(quality_score, 1)
                    })

            # Categorize flags
            flag_summary = Counter()
            for review in flagged_reviews:
                for flag in review["flags"]:
                    flag_summary[flag] += 1

            result = {
                "total_reviews_analyzed": len(reviews),
                "total_flagged": len(flagged_reviews),
                "flag_summary": dict(flag_summary),
                "flagged_reviews": flagged_reviews,
                "criteria_used": default_criteria
            }

            return result

        except Exception as e:
            return {"error": f"Failed to identify problematic reviews: {str(e)}"}
