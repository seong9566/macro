You are reviewing a plan to add movement prediction to a game macro's monster tracker.

## Context
This is a Python macro for an online game (온라인삼국지2). It uses template matching (OpenCV) to detect wolves on screen and clicks them to attack. The problem is that monsters move between detection and clicking, causing missed clicks.

## Current Code Files
Read these files to understand the codebase:
- monster_tracker.py (detection + tracking logic)
- macro_engine.py (hunt loop that calls tracker then clicks)
- config.py (all configuration constants)
- clicker.py (click methods)

## The Plan
Read this file for the proposed improvement plan:
- .omc/plans/movement-prediction-plan.md

## Your Review Task
1. Read all source files above to fully understand the current code
2. Read the plan document
3. Evaluate each of the 4 proposed approaches (A, B, C, D) considering:
   - This is a game with monsters that move at moderate speed
   - Template matching takes ~50-200ms
   - The macro runs at roughly 3 iterations/sec
   - The game uses pixel-perfect click detection
4. Assess whether the recommended approach (A+D: velocity prediction + pipeline optimization) is optimal, or if another approach would be better
5. Identify any flaws, edge cases, or improvements in the implementation plan
6. Write your complete review to: .omc/plans/codex-review-result.md

Format your review as:
## Overall Assessment
## Approach Evaluation (rate each A/B/C/D)
## Recommended Optimal Approach (with justification)
## Implementation Concerns
## Suggested Improvements to the Plan
