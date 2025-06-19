# 🎯 Canvas MCP Server - New Rubric Features

## Overview
The Canvas MCP server now includes comprehensive rubric management tools that enable detailed grading workflows using Canvas rubrics. These tools integrate seamlessly with the existing modular architecture.

## 🔧 New Rubric Tools

### 1. `list_assignment_rubrics`
**Purpose**: Get rubrics attached to a specific assignment

**Parameters**:
- `course_identifier`: Canvas course code or ID
- `assignment_id`: Canvas assignment ID

**Example Usage**:
```json
{
  "course_identifier": "badm_350_120245_236093",
  "assignment_id": "12345"
}
```

**Returns**: 
- Rubric settings (grading usage, points, display options)
- Criteria overview with points and rating levels
- Total possible points and criteria count

---

### 2. `get_rubric_details`
**Purpose**: Get detailed rubric criteria and scoring information

**Parameters**:
- `course_identifier`: Canvas course code or ID  
- `rubric_id`: Canvas rubric ID

**Example Usage**:
```json
{
  "course_identifier": "badm_350_120245_236093",
  "rubric_id": "67890"
}
```

**Returns**:
- Complete rubric metadata (title, context, points)
- Detailed criteria with descriptions and rating levels
- Full scoring breakdown for each criterion

---

### 3. `get_submission_rubric_assessment`
**Purpose**: Get rubric assessment scores for a specific submission

**Parameters**:
- `course_identifier`: Canvas course code or ID
- `assignment_id`: Canvas assignment ID
- `user_id`: Canvas user ID of the student

**Example Usage**:
```json
{
  "course_identifier": "badm_350_120245_236093", 
  "assignment_id": "12345",
  "user_id": "54321"
}
```

**Returns**:
- Submission details (dates, score)
- Complete rubric assessment with points awarded
- Rating descriptions and comments for each criterion
- Total rubric points

---

### 4. `grade_with_rubric`
**Purpose**: Submit grades using rubric criteria

**Parameters**:
- `course_identifier`: Canvas course code or ID
- `assignment_id`: Canvas assignment ID
- `user_id`: Canvas user ID of the student  
- `rubric_assessment`: JSON string with assessment data
- `comment`: Optional overall comment

**Rubric Assessment Format**:
```json
{
  "criterion_id_1": {
    "points": 8,
    "comments": "Excellent analysis with clear supporting evidence"
  },
  "criterion_id_2": {
    "points": 6,
    "comments": "Good organization, minor formatting issues"
  }
}
```

**Example Usage**:
```json
{
  "course_identifier": "badm_350_120245_236093",
  "assignment_id": "12345", 
  "user_id": "54321",
  "rubric_assessment": "{\"123\": {\"points\": 8, \"comments\": \"Great work!\"}, \"124\": {\"points\": 7, \"comments\": \"Minor issues with citations\"}}",
  "comment": "Overall strong submission. Keep up the good work!"
}
```

**Returns**:
- Confirmation of successful grading
- Summary of points awarded per criterion
- Total rubric score and grading timestamp

## 🔄 Typical Rubric Workflow

### 1. **Discover Rubrics**
```bash
# Find rubrics for an assignment
list_assignment_rubrics(course_id, assignment_id)
```

### 2. **Understand Criteria** 
```bash
# Get detailed rubric breakdown
get_rubric_details(course_id, rubric_id)
```

### 3. **Review Existing Grades**
```bash  
# Check current rubric assessment
get_submission_rubric_assessment(course_id, assignment_id, user_id)
```

### 4. **Submit New Grades**
```bash
# Grade using rubric criteria
grade_with_rubric(course_id, assignment_id, user_id, assessment_json, comment)
```

## 🎯 Key Features

### **Comprehensive Error Handling**
- Validates rubric existence and accessibility
- Provides clear error messages for missing data
- Handles JSON parsing errors gracefully

### **Rich Data Display**
- Formatted rubric criteria with descriptions
- Point breakdowns and rating level details
- Student-friendly assessment summaries

### **Flexible Grading**
- Support for partial points within criteria
- Individual comments per criterion
- Overall submission comments

### **Integration Ready**
- Follows modular architecture patterns
- Consistent with existing tool design
- Compatible with current caching and validation systems

## 📊 Benefits for Educators

### **Streamlined Grading**
- View complete rubric structure before grading
- Apply consistent criteria across submissions
- Track detailed feedback per learning objective

### **Quality Assurance**  
- Review existing rubric assessments
- Ensure grading consistency across sections
- Maintain detailed grading records

### **Efficient Workflows**
- Batch process rubric-based grading
- Integrate with external grading tools
- Export detailed assessment data

## 🔧 Technical Implementation

### **Architecture**
- **Module**: `tools/rubrics.py`
- **Registration**: Integrated in `canvas_server_refactored.py`
- **Dependencies**: Uses existing core utilities (client, cache, validation)

### **API Integration**
- **Canvas Rubrics API**: Full endpoint coverage
- **Assignment Integration**: Seamless rubric discovery
- **Submission API**: Complete assessment workflow

### **Data Structures**
- **Type Safety**: Comprehensive parameter validation
- **Error Handling**: Graceful API failure management  
- **Response Formatting**: Consistent, readable output

## 🚀 Getting Started

1. **Update Server**: Use `canvas_server_refactored.py`
2. **Test Connection**: Verify Canvas API access
3. **Find Assignment**: Use existing assignment tools
4. **Explore Rubrics**: Start with `list_assignment_rubrics`
5. **Grade Students**: Use `grade_with_rubric` for assessment

The new rubric features integrate seamlessly with the existing Canvas MCP server, providing a complete grading solution for rubric-based assessments! 🎉