# ASTCSS Reflexive Prompting & Error-Handling Catalog

This document defines the formal multi-turn prompt templates used to guide models through **Shot 1 (Initial Generation) $\rightarrow$ Execution Feedback $\rightarrow$ Shot 2 (Self-Correction & Repair)**.

---

## 1. System Prompt & Environment Contract

The base system prompt establishes the single-line output contract for Shot 1, while preparing the model to interpret structured environment feedback during Turn 2.

### System Prompt (`system`)
```text
You translate a developer's plain-English request into ONE astcss selector over a codebase AST.
Reply with the selector only: one line, no quotes, no backticks, no explanation.

If your selector fails to parse, returns 0 matches, or violates constraints, an [Execution Feedback] or [ASTCSS Syntax Error] diagnostic will be provided. In response to feedback, output ONLY the revised, corrected ASTCSS selector.
```

---

## 2. Error Prompt Taxonomy & Templates

### Category 1: "This Failed to Parse" (Syntax & Dialect Errors)

Triggered when the AST parser or DuckDB ASTCSS macro rejects the selector due to unclosed delimiters, invalid characters, or unsupported syntax.

#### Template:
```text
<|im_start|>user
[ASTCSS Syntax Error]
The selector '{shot1_selector}' failed to parse:
Error: {error_details}

Guidance: Ensure all brackets '[...]' and quotes are properly balanced. Combinators must use valid symbols ('>', '+', '~', or space). Supported pseudo-classes are :has(), :not(), :is(), :where(), :scope(), :exported, :is-called.
Please output a corrected, parseable ASTCSS selector.
<|im_end|>
<|im_start|>assistant
```

#### Empirical Example 1 (Unclosed Attribute Bracket):
* **User Intent:** `functions with name starting with get`
* **Shot 1 Output:** `.fn[name^="get"`
* **Turn 2 Feedback:**
  ```text
  <|im_start|>user
  [ASTCSS Syntax Error]
  The selector '.fn[name^="get' failed to parse: malformed selector — unclosed bracket or quote near "[".
  Please ensure all brackets '[' and ']' and quotes are properly closed. Output the corrected selector.
  <|im_end|>
  <|im_start|>assistant
  .fn[name^="get"]
  ```

#### Empirical Example 2 (Unsupported Pseudo-Class):
* **User Intent:** `classes with a decorator on them`
* **Shot 1 Output:** `.class:decorated`
* **Turn 2 Feedback:**
  ```text
  <|im_start|>user
  [ASTCSS Unsupported Pseudo-Class]
  The selector '.class:decorated' failed to execute: unknown pseudo-class ':decorated'.
  - Supported pseudo-classes: :has(), :not(), :is(), :where(), :scope(), :exported.
  - To match decorators/annotations, use attribute filter [annotation] or combinator 'decorated_definition > .class'.
  Please output the revised selector.
  <|im_end|>
  <|im_start|>assistant
  decorated_definition > .class
  ```

---

### Category 2: "This Failed to Return Anything" (0 Matches / Specificity Errors)

Triggered when the selector is syntactically valid, but returns `0` nodes from the target codebase AST. The feedback engine performs AST introspection to identify whether the failure was caused by naming assumptions, cross-language idiom transfer, or raw Tree-sitter mismatches.

#### Sub-Case 2A: Name Over-Specificity (Prefix & Identifier Introspection)

* **User Intent:** `the update functions`
* **Shot 1 Output:** `.fn#update`
* **Engine Introspection:** Found functions `['update_user', 'update_settings', 'update_record']`.
* **Turn 2 Feedback:**
  ```text
  <|im_start|>user
  [Execution Feedback: 0 Matches]
  The selector '.fn#update' returned 0 matches in the target file AST.
  - Diagnostic Hint: Found related identifiers in the codebase: ['update_user', 'update_settings', 'update_record'].
  - The selector '#update' required an exact name match. Consider using a prefix attribute selector [name^="update_"] or regex [name~="update"].
  Please revise the selector to match the intended functions.
  <|im_end|>
  <|im_start|>assistant
  .fn[name^="update_"]
  ```

#### Sub-Case 2B: Cross-Language Framework / Method Transfer

* **User Intent:** `classes without a constructor`
* **Shot 1 Output:** `.class:not(:has(.fn#__constructor))`
* **Engine Introspection:** Target language is Python.
* **Turn 2 Feedback:**
  ```text
  <|im_start|>user
  [Execution Feedback: 0 Matches]
  Selector '.fn#__constructor' returned 0 matches inside '.class'.
  - Diagnostic Hint: In Python, constructor methods are named '__init__', not '__constructor'.
  Revise the constructor selector to match Python class initialization methods.
  <|im_end|>
  <|im_start|>assistant
  .class:not(:has(.fn#__init__))
  ```

* **User Intent:** `loops that append to a list`
* **Shot 1 Output:** `.loop:has(.call#push)`
* **Engine Introspection:** Target language is Python.
* **Turn 2 Feedback:**
  ```text
  <|im_start|>user
  [Execution Feedback: 0 Matches]
  Selector '.call#push' returned 0 matches inside '.loop'.
  - Diagnostic Hint: In Python, list element insertion uses '.call#append' or '.call#extend', not 'push'.
  Please revise the selector using Python method conventions.
  <|im_end|>
  <|im_start|>assistant
  .loop:has(.call#append)
  ```

#### Sub-Case 2C: Module Receiver vs Function Name

* **User Intent:** `classes whose code calls into the json module`
* **Shot 1 Output:** `.class:has(.call#json)`
* **Engine Introspection:** Found method calls `json.dumps` and `json.loads`.
* **Turn 2 Feedback:**
  ```text
  <|im_start|>user
  [Execution Feedback: 0 Matches]
  Selector '.call#json' returned 0 matches.
  - Diagnostic Hint: '.call#json' matches direct function calls named 'json()'.
  - To match calls where 'json' is the receiver module (e.g., json.loads(), json.dumps()), use the receiver attribute filter: '.call[receiver="json"]'.
  Please revise the selector.
  <|im_end|>
  <|im_start|>assistant
  .class:has(.call[receiver="json"])
  ```

#### Sub-Case 2D: Semantic Shorthand vs Raw Tree-Sitter Node

* **User Intent:** `the finally blocks`
* **Shot 1 Output:** `finally_statement`
* **Engine Introspection:** ASTCSS semantic class `.finally` expected.
* **Turn 2 Feedback:**
  ```text
  <|im_start|>user
  [Execution Feedback: 0 Matches]
  The query 'finally_statement' returned 0 matches in ASTCSS.
  - Diagnostic Hint: In ASTCSS, prefer language-agnostic semantic shorthands. Use '.finally' instead of raw Tree-sitter 'finally_statement'.
  Please output the semantic selector.
  <|im_end|>
  <|im_start|>assistant
  .finally
  ```

---

### Category 3: "Graph Direction Inversion" (Callers vs Callees)

Triggered when the model confuses incoming callers (`::callers`) with outgoing callees (`::callees`).

#### Empirical Example 1 (Outgoing Calls / Callees):
* **User Intent:** `what are all the functions called by validate_email`
* **Shot 1 Output:** `.fn#validate_email::callers`
* **Turn 2 Feedback:**
  ```text
  <|im_start|>user
  [Execution Feedback: Graph Direction Inversion]
  Query '.fn#validate_email::callers' traversed incoming callers (functions that call validate_email).
  - The request asks for functions CALLED BY validate_email (outgoing calls / callees).
  - Use the outgoing edge '::callees' or child traversal '.fn#validate_email .call'.
  Revise the selector direction.
  <|im_end|>
  <|im_start|>assistant
  .fn#validate_email::callees
  ```

#### Empirical Example 2 (Incoming Callers):
* **User Intent:** `what functions call escape_raw_string_delimiter`
* **Shot 1 Output:** `.call#escape_raw_string_delimiter`
* **Turn 2 Feedback:**
  ```text
  <|im_start|>user
  [Execution Feedback: Target Mismatch]
  Query '.call#escape_raw_string_delimiter' returned call expressions, but the intent asks for the ENCLOSING FUNCTIONS that make those calls.
  - To query functions that call a target, use the caller relation: '.fn#escape_raw_string_delimiter::callers'.
  Please revise the selector.
  <|im_end|>
  <|im_start|>assistant
  .fn#escape_raw_string_delimiter::callers
  ```

---

### Category 4: "Result Too Broad" (Over-Matching Universe)

Triggered when a query matches $>50$ nodes or returns entire module scopes without necessary filtering.

#### Template:
```text
<|im_start|>user
[Execution Feedback: Result Too Broad]
The selector '{shot1_selector}' matched {count} nodes (e.g. {sample_node_1}, {sample_node_2}...).
The query lacks needed constraints. Consider adding specific name attributes ([name=...]), module/receiver scopes ([receiver=...]), or parent combinators (A > B).
Revise the selector to target only the intended nodes.
<|im_end|>
<|im_start|>assistant
```

---

## 3. Implementation in the Live System

These prompts are natively generated and evaluated by:
1. **Live Evaluation Engine:** [`tune/reflexive_repair.py`](file:///home/teague/Projects/astcss-eval/trees/tune/setup/tune/reflexive_repair.py) (`evaluate_reflexive_repair()`).
2. **Fine-Tuning Dataset Generator:** [`tune/build_reflexive_dataset.py`](file:///home/teague/Projects/astcss-eval/trees/tune/setup/tune/build_reflexive_dataset.py) (`build_dataset()`).
3. **Unit Test Suite:** [`test_reflexive_repair.py`](file:///home/teague/Projects/astcss-eval/trees/tune/setup/test_reflexive_repair.py).
