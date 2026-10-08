Prof. Okafor, week 1 (Strang ch. 1–2). Ax = **b** has a **row picture** (each equation is a line/plane, the solution is where they meet) and a **column picture** (**b** is a combination of the columns of A).
Elimination: subtract multiples of the pivot row to get zeros below each pivot, giving an upper triangular U. Then back-substitute. A zero in a pivot spot means swap rows. If no swap fixes it, the matrix is singular.

rref steps: (1) get a pivot in the leftmost column, (2) zeros below it, (3) move right/down and repeat, (4) scale each pivot to 1, (5) zeros *above* every pivot too.
Pivot columns ↔ pivot variables; the other columns ↔ **free variables**.
Okafor's three cases for Ax = **b**: a row `[0 0 … 0 | c]` with c ≠ 0 → **no solution**; no free variables → **exactly one** solution; free variables (and consistent) → **infinitely many**.
On exams he wants every row operation written out, like R2 → R2 − 3R1.

AB is defined when columns of A = rows of B. Entry (i, j) = row i of A · column j of B. **AB ≠ BA** in general.
Inverse: A⁻¹A = I. A square matrix is invertible ⇔ n pivots ⇔ det ≠ 0 ⇔ N(A) = {**0**}.
To find A⁻¹: row-reduce [A | I] to [I | A⁻¹] (Gauss–Jordan).
Rules: (AB)⁻¹ = B⁻¹A⁻¹ (order flips), (Aᵀ)⁻¹ = (A⁻¹)ᵀ. For 2×2: [[a, b], [c, d]]⁻¹ = 1/(ad − bc) · [[d, −b], [−c, a]].

A **subspace** is a subset that is itself a vector space. Three-step test:
1. Contains the zero vector.
2. Closed under addition (**u**, **v** in it → **u** + **v** in it).
3. Closed under scalar multiplication (c**v** in it).
Okafor: "always check zero first — it kills most non-examples in one line." Examples: a line through the origin in ℝ² is a subspace; the line y = x + 1 is not (no **0**); the first quadrant is not (fails with c = −1).
Proof format on exams: take arbitrary **u**, **v**, c and show each property, don't just test numbers.

- **C(A)**, column space: all combinations of A's columns. Ax = **b** is solvable ⇔ **b** is in C(A). Basis = the *original* columns of A that are pivot columns in rref (not the rref columns!).
- **N(A)**, null space: all **x** with Ax = **0**. Always a subspace.
How to find N(A): rref A, then for each free variable set it to 1 and the other free variables to 0, and solve for the pivot variables. These **special solutions** are a basis for N(A).
Example from class: A = [[1, 2, 3], [2, 4, 7]] → rref [[1, 2, 0], [0, 0, 1]], free variable x₂, special solution (−2, 1, 0). So N(A) is the line through (−2, 1, 0).

**Rank** r = number of pivots. For an m×n matrix: dim C(A) = r and dim N(A) = n − r (**rank–nullity**).
Complete solution of Ax = **b**: **x** = **x**_p + **x**_n, where **x**_p is one particular solution (set free variables to 0) and **x**_n is any vector in N(A).
Full column rank (r = n): no free variables, 0 or 1 solution. Full row rank (r = m): a solution for every **b**.

Vectors **v**₁…**v**ₙ are **linearly independent** if the only combination giving **0** is all-zero coefficients.
Test: put the vectors as columns of A and rref. Independent ⇔ every column is a pivot column ⇔ N(A) = {**0**} ⇔ rank = n. More than m vectors in ℝᵐ are always dependent.
A **basis** is an independent set that spans the space. **Dimension** = number of vectors in any basis. Problem Set 5 (due Oct 8) is all of this.

Midterm 1: Tue Oct 13, in class, 75 minutes, closed book, no calculators, no note sheet. Okafor said it will have five problems: (1) solve a system with rref and describe the solution set, (2) find bases for N(A) and C(A), (3) prove whether a set is a subspace, (4) compute an inverse or show none exists, (5) true/false with a one-line justification. Steps matter: a bare answer gets at most half credit. Extra review session Sun Oct 11, 14:00–15:30, Science Center 101. Best practice: Strang 2.2, 2.5, 3.1, 3.2 and the posted practice midterm.
