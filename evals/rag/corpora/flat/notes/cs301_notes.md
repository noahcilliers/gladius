Prof. Chen, weeks 1. A **relation** is a table, a **tuple** is a row, an **attribute** is a column. The schema is the structure; the instance is the data at one moment.
- **Superkey:** any set of columns that uniquely identifies a row.
- **Candidate key:** a minimal superkey (drop any column and it stops being unique).
- **Primary key:** the candidate key we pick. Never NULL.
- **Foreign key:** a column that must match a primary key in another table (e.g. `enrollments.student_id → students.id`). Enforces referential integrity.
Chen: "a table without a key is a bag, not a relation."

Entities are rectangles, attributes are ovals, relationships are diamonds. Cardinality: 1:1, 1:N, M:N. A weak entity (double rectangle) can't be identified without its owner (e.g. a dorm room needs its building).
Turning an ER diagram into tables:
- 1:N → put a foreign key on the "many" side.
- M:N → make a **junction table** with both foreign keys as a composite primary key (students ↔ courses becomes `enrollments`).
Chen said milestone 1 loses points if any relationship line is missing its cardinality label.

No class Sep 7 (Labor Day). A functional dependency X → Y means X determines Y.
- **1NF:** every value is atomic. No lists in a cell.
- **2NF:** 1NF, and no non-key column depends on only *part* of a composite key.
- **3NF:** 2NF, and no non-key column depends on another non-key column (no transitive dependencies).
Example from lecture: `enrollments(student_id, course_id, student_name, grade)` breaks 2NF because student_name depends only on student_id. Fix: move student_name into `students`.
Chen's shortcut: "every non-key column must depend on the key, the whole key, and nothing but the key." The course project schema has to be in 3NF.

SQL runs in this order, not the order you write it: FROM → WHERE → GROUP BY → HAVING → SELECT → ORDER BY → LIMIT. That's why a SELECT alias can't be used in WHERE but can be used in ORDER BY.
NULL means "unknown", so `NULL = NULL` is unknown, not true. Use `IS NULL` / `IS NOT NULL`. `COUNT(*)` counts rows; `COUNT(grade)` skips NULLs, so it counts only finished courses in the enrollments table. Aggregates like AVG ignore NULLs too.

- **INNER JOIN:** only rows with a match on both sides.
- **LEFT JOIN:** every row from the left table, NULLs where the right side has no match. Use it for "students with no enrollments": `LEFT JOIN enrollments e ON ... WHERE e.student_id IS NULL`.
- **FULL OUTER JOIN:** everything from both sides (SQLite only added it in 3.39).
- **Self join:** join a table to itself with two aliases, e.g. pairs of students in the same major.
Chen's big gotcha: a filter on the right table in WHERE (`WHERE e.semester = 'Fall 2026'`) silently turns a LEFT JOIN into an inner join. Put that condition in the ON clause instead. HW3 Q2 tests exactly this.

- **Scalar subquery:** returns one value, e.g. `WHERE gpa > (SELECT AVG(gpa) FROM students)`.
- **IN:** `WHERE id IN (SELECT student_id FROM enrollments)`.
- **EXISTS:** true if the subquery returns any row. Usually **correlated** (refers to the outer query), so it re-runs per outer row.
- **NOT IN trap:** if the subquery returns any NULL, `NOT IN` returns no rows at all. Use `NOT EXISTS` instead.
Chen's HW3 hints: Q4 ("students above their major's average GPA") needs a correlated subquery. Q5 can be done with either a join or EXISTS, and she wants one sentence explaining which you picked and why.

WHERE filters **rows before** grouping. HAVING filters **groups after** aggregation, so only HAVING can use COUNT/AVG/SUM.
Rule: every column in SELECT must be either in GROUP BY or inside an aggregate.
Lecture example, majors whose average GPA is above 3.5 with at least 5 students:
`SELECT major, AVG(gpa) FROM students GROUP BY major HAVING AVG(gpa) > 3.5 AND COUNT(*) >= 5;`
Enrollment count per course: join courses to enrollments, `GROUP BY c.id, c.code`, then `COUNT(e.student_id)`. Use a LEFT JOIN if courses with zero students should show 0.

An index is like the index at the back of a textbook: a sorted structure (usually a **B+ tree**) that lets the database jump to matching rows instead of scanning the whole table.
- Speeds up WHERE lookups, JOIN keys and ORDER BY on the indexed column.
- Costs disk space and slows INSERT/UPDATE/DELETE, because the index has to be updated too.
- Primary keys get an index automatically. Foreign keys usually don't, but often should.
- Use `EXPLAIN QUERY PLAN` (SQLite) to see "SCAN" (full table) vs "SEARCH ... USING INDEX".
Milestone 2 needs each index justified with before/after EXPLAIN output. More on this after the midterm.

The midterm is Wed Oct 21, in class, 50 minutes. Chen said there are four question types: (1) write 3–4 SQL queries on paper, (2) draw an ER diagram from a short description, (3) normalize a table to 3NF, (4) trace a query and write its exact output. **No window functions and no indexes on the midterm.** Old midterm with solutions is on the course site. Review session: Mon Oct 19, 18:00–19:30, Engineering Hall 101 (clashes with my library shift, so ask to swap). Allowed: one double-sided handwritten note sheet.
