# Example Prompts by Route

Use these as **router centroid examples** (20–50 per route is the target; these are starters) and as **demo prompts**.

Base: `unsloth/Llama-3.2-3B-Instruct`

| Route | Adapter |
|---|---|
| `math` | SriSanth2345/LLAMA-3.2-3B-MathInstruct_LORA_SFT |
| `sql` | BY-ALF/llama-3.2-3b-sql-lora (or jeeejeee/llama32-3b-text2sql-spider) |
| `techwriter` | Shankarblr/Llama-3.2-3B-TechWriter-LoRA |
| `creative` | Brie (Llama 3.2 3B version; verify base in adapter_config.json) |
| `base` | No adapter (fallback) |

---

## math

- A train leaves at 3pm going 60 mph. Another leaves the same station at 4pm going 80 mph. When does the second train catch up?
- Solve for x: 3x² − 12x + 9 = 0
- What's the derivative of x³·sin(x)?
- If I score 78, 85, and 91 on three exams, what do I need on the fourth to average 88?
- A shirt costs $40 after a 20% discount. What was the original price?
- Find the area of a triangle with sides 7, 8, and 9.
- How many ways can 5 people sit in a row if two of them must sit together?
- Integrate 2x·e^(x²) dx.
- A recipe needs 3/4 cup of sugar for 12 cookies. How much for 30 cookies?
- What is the probability of rolling a sum of 7 with two dice?

## sql

- Given `CREATE TABLE students (id INT, name TEXT, major TEXT, gpa REAL)`, find the average GPA per major.
- Write a query to get the top 5 customers by total order amount.
- Fix this query: `SELECT name, COUNT(*) FROM orders GROUP BY customer_id`
- How do I find duplicate emails in a users table?
- Given `employees(id, name, department, salary)`, list everyone who earns more than their department's average.
- Write a query that joins `orders` and `customers` and returns customers with no orders.
- Count how many students are enrolled in each course, sorted descending.
- Delete all rows from `sessions` older than 30 days.
- Given `products(id, name, price, category)`, get the most expensive product in each category.
- Write a SQL query to find the second highest salary.

## techwriter

- Write a product brief for a 100GbE network adapter.
- Draft a datasheet feature list for a 48-port Ethernet switch.
- Write an application note explaining how to configure link aggregation on a switch.
- Write the CLI user-guide section for setting a VLAN on a host adapter.
- Summarize the key specs of a PCIe Gen5 storage controller for a datasheet.
- Draft release notes for a firmware update that improves RDMA latency.
- Write a feature overview of RoCE v2 support for a data-center NIC.
- Write a quick-start guide for installing a converged network adapter.

## creative

- What would Heidegger say about doomscrolling?
- Brainstorm concepts for a short story about memory and identity.
- Write a contemplative piece on why deadlines feel heavier at night.
- Is boredom a kind of freedom? Explore the idea.
- Give me five speculative premises for a story set in a city that forgets itself every night.
- Reflect on what it means to "own" a thought.
- Write a short meditative passage about waiting for a bus in the rain.
- How might Simone de Beauvoir think about social media identity?

## base (no adapter)

- Write an email to my professor asking for an extension.
- Summarize the causes of World War I in 3 bullet points.
- What's a good weekly study schedule for finals?
- Explain what a mitochondrion does in simple terms.
- Give me tips for my first internship interview.
- Translate "Where is the library?" into Spanish.
- What should I pack for a weekend camping trip?
- Rewrite this sentence to sound more professional: "hey can u send the notes"

---

## Demo prompts (ambiguous / edge cases)

Use these live to show the router is measuring similarity, not matching keywords. Display the top-2 scores.

| Prompt | Expected behavior |
|---|---|
| Write a query to calculate each student's GPA, then explain the math. | `sql` vs `math`, close scores |
| Write a poem about prime numbers. | `creative` vs `math` |
| Explain what a database index is to a beginner. | `base` or low-confidence `sql` |
| Write a product brief, but make it philosophical. | `techwriter` vs `creative` |
| hey whats up | `base` (low similarity to all adapters) |
| What is 2 + 2? | `math` (sanity check) |

## Eval split

Keep centroid prompts and eval prompts **separate**. If the router is scored on the same prompts used to build its centroids, routing accuracy will be inflated.
