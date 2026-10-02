# Example Prompts by Route

Use these as **router centroid examples** (20–50 per route is the target; these are starters) and as **demo prompts**.

Base: `meta-llama/Llama-3.2-3B-Instruct` (served as `bartowski/Llama-3.2-3B-Instruct-GGUF`, Q4_K_M)

| Route | Adapter | Size | LoRA |
|---|---|---|---|
| `math` | SriSanthM/LLAMA-3.2-3B-MathInstruct_LORA_SFT | 49 MB | r=8, all linear |
| `sql` | ~~BY-ALF/llama-3.2-3b-sql-lora~~ dropped: lost to base (73% vs 93%). SQL prompts are answered by the base model | 18 MB | r=16, q/v |
| `techwriter` | Shankarblr/Llama-3.2-3B-TechWriter-LoRA | 97 MB | r=16, all linear |
| `creative` | closestfriend/brie-llama-3b | 18 MB | r=16, q/v |
| `coding` | yusifnuri/Llama-3.2-3B-Instruct_code_generation | 37 MB | r=16, q/k/v/o |
| `base` | No adapter (fallback) | | |

Don't use jeeejeee/llama32-3b-text2sql-spider: it's 1.6 GB because it also trains `embed_tokens` and `lm_head`.

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
- A car loses 15% of its value each year. What is a $20,000 car worth after 3 years?
- What is the sum of the first 50 positive integers?
- Simplify (x² − 9)/(x − 3).
- A rectangle's length is twice its width and its perimeter is 36 cm. Find its area.
- If 3 workers paint a house in 8 days, how long would 4 workers take?
- What is 15% of 240?
- Convert 0.375 to a fraction in lowest terms.
- Solve the system: 2x + y = 7 and x − y = 2.
- What is the limit of sin(x)/x as x approaches 0?
- I invest $1,000 at 5% interest compounded annually. How much do I have after 10 years?
- A bag has 4 red and 6 blue marbles. What's the probability of drawing two red without replacement?
- How long does it take to drive 210 miles at 55 mph?

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
- Write a query to find all orders placed in the last 7 days.
- Given `enrollments(student_id, course_id, grade)`, find students who took more than 3 courses.
- How do I rename a column in PostgreSQL?
- Write a query that returns the running total of sales by date.
- Increase the price of every product in the 'electronics' category by 10%.
- Create a table for blog posts with a foreign key to an authors table.
- Write a query to rank employees by salary within each department.
- Select all users whose email ends with '@gmail.com'.
- Show the difference between LEFT JOIN and INNER JOIN with an example query.
- Write a query to pivot monthly revenue into one column per month.
- Find customers who placed orders in both 2023 and 2024.
- Given `logins(user_id, login_time)`, count daily active users.

## techwriter

- Write a product brief for a 100GbE network adapter.
- Draft a datasheet feature list for a 48-port Ethernet switch.
- Write an application note explaining how to configure link aggregation on a switch.
- Write the CLI user-guide section for setting a VLAN on a host adapter.
- Summarize the key specs of a PCIe Gen5 storage controller for a datasheet.
- Draft release notes for a firmware update that improves RDMA latency.
- Write a feature overview of RoCE v2 support for a data-center NIC.
- Write a quick-start guide for installing a converged network adapter.
- Write a product overview for a dual-port 25GbE SFP28 NIC.
- Draft the "Key Features" section of a datasheet for a SmartNIC.
- Write the installation prerequisites for a PCIe network adapter driver on Linux.
- Write a troubleshooting section for link-down errors on a fiber transceiver.
- Draft a technical brief comparing iSCSI offload and NVMe-over-Fabrics offload.
- Write release notes for a driver update that adds SR-IOV support.
- Write a configuration guide for enabling jumbo frames on a 10GbE adapter.
- Summarize the power and thermal specifications of a top-of-rack switch for a datasheet.
- Write an application note on tuning interrupt moderation for low-latency workloads.
- Draft a solution brief for running a NIC with DPDK in a Kubernetes cluster.
- Describe the hardware specifications of a 400GbE QSFP-DD optical module for a datasheet.
- Write an FAQ section for customers upgrading switch firmware.
- Write technical documentation for the parse_config() function in my project.
- Write documentation for my compute_average function.
- Write an API reference for the load_data() function in utils.py.
- Document the functions in my project code for a README.
- Write a user-guide section explaining how to use my grading script.
- Write reference documentation for the helper function in my notes.
- Write technical documentation for a Python function from my course project.
- Write developer documentation for the functions in my code notes.

## creative

- What would Heidegger say about doomscrolling?
- Brainstorm concepts for a short story about memory and identity.
- Write a contemplative piece on why deadlines feel heavier at night.
- Is boredom a kind of freedom? Explore the idea.
- Give me five speculative premises for a story set in a city that forgets itself every night.
- Reflect on what it means to "own" a thought.
- Write a short meditative passage about waiting for a bus in the rain.
- How might Simone de Beauvoir think about social media identity?
- What would Camus say about the daily commute?
- Write a short reflective essay on the beauty of unfinished things.
- Brainstorm ten titles for a novel about a lighthouse keeper who collects lost letters.
- Is nostalgia a form of time travel? Reflect on it.
- How might Nietzsche react to productivity apps?
- Write a lyrical paragraph about the first snowfall in a quiet town.
- Explore the idea that every map is also a story.
- Give me three surreal story openings about a library that rearranges itself overnight.
- What does silence sound like? Write a meditation on it.
- Reflect on the ethics of remembering versus forgetting.
- Imagine a dialogue between Socrates and a smartphone.
- Write a contemplative piece about strangers sharing a night train.

## coding

- Write a Python function that checks whether a string is a palindrome.
- Complete this function: def fibonacci(n): """Return the nth Fibonacci number."""
- Write a Python function to merge two sorted lists into one sorted list.
- def is_prime(n): # return True if n is prime
- Write a Python function that removes duplicates from a list while keeping the order.
- Implement a Python function that counts the vowels in a string.
- Write a function in Python that flattens a nested list.
- Complete the function: def two_sum(nums, target): """Return indices of the two numbers that add up to target."""
- Write a Python function to reverse the words in a sentence.
- Write a Python function that returns the largest element in a list without using max().
- Implement binary search in Python.
- Write a Python function that converts a Roman numeral to an integer.
- def count_words(text): # return a dict of word frequencies
- Write a Python function to check if two strings are anagrams.
- Write a Python function that returns the n most common words in a text file.
- Implement a Python function that validates balanced parentheses in a string.
- Write a Python function that computes the factorial of a number recursively.
- Write a Python class for a stack with push, pop and peek.
- Write a Python function that transposes a matrix.
- Write a Python script that reads a CSV file and prints the average of one column.

## base (no adapter)

- Write an email to my professor asking for an extension.
- Summarize the causes of World War I in 3 bullet points.
- What's a good weekly study schedule for finals?
- Explain what a mitochondrion does in simple terms.
- Give me tips for my first internship interview.
- Translate "Where is the library?" into Spanish.
- What should I pack for a weekend camping trip?
- Rewrite this sentence to sound more professional: "hey can u send the notes"
- How do I make a monthly budget as a college student?
- Write a thank-you note to my roommate for helping me move.
- What's the difference between weather and climate?
- Give me a 3-day beginner workout plan.
- How do I cite a website in APA format?
- Suggest a few easy dinners I can make with rice and eggs.
- What are good ways to stay focused while studying?
- Explain how vaccines work in simple terms.
- Draft a LinkedIn message asking an alum for a coffee chat.
- What's the capital of Australia?
- How should I prepare for a group presentation?
- Any tips for sleeping better during exam week?

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

## Personal prompts (RAG eval)

These test step 4b against `data/student/`. **Do not use these as router centroid examples.** Score each one on two things: did the right chunks come back, and is the answer correct with RAG on vs. off.

| Prompt | Expected route | Expected chunks |
|---|---|---|
| Write an email to my databases professor asking for an extension on HW3. | `base` | CS 301 — Late policy, late days and how to ask for an extension; CS 301 — Assignment deadlines |
| When is my linear algebra midterm and what does it cover? | `base` | MATH 221 — Problem set and exam dates |
| Make me a study plan for next week. | `base` | profile; MATH 221 dates; CS 301 deadlines; PHIL 150 Essay 1 |
| What's due before the end of October? | `base` | CS 301 — Assignment deadlines; MATH 221 dates; PHIL 150 Essay 1 |
| When are Prof. Okafor's office hours? | `base` | MATH 221 — Course overview and instructor |
| Count how many students are enrolled in each course this semester. | `sql` | CS 301 — University class database schema |
| Which bike stations have the most rides starting from them? | `sql` | CS 301 — Bike-share project database schema |
| Help me outline my Heidegger essay. | `creative` | PHIL 150 — Essay 1 prompt and requirements |
| What's the derivative of x³·sin(x)? | `math` | none (negative control: nothing should be injected) |
| hey whats up | `base` | profile only (no course chunk should clear the threshold) |

Expected answers are in the corpus files. For example, the extension email should name Prof. Chen, mention the 48-hour rule, and reference the Oct 9 HW3 deadline.

## Eval split

Keep centroid prompts and eval prompts **separate**. If the router is scored on the same prompts used to build its centroids, routing accuracy will be inflated.
