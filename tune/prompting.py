"""One prompt format for training and local generation, so they cannot drift apart.

The text is the tokenizer's chat template with the generation prompt added and thinking
turned off, followed (in training) by the selector and the end-of-turn token. Training on
`prompt_text(...) + selector + <|im_end|>` and generating from `prompt_text(...)` means the
model sees byte-identical prefixes in both. Bump FORMAT_VERSION whenever this changes; it
is recorded in every run's meta.json and every dataset-derived adapter.
"""
FORMAT_VERSION = "chat-template+gen-prompt+nothink/v1"

# Qwen3.5's multimodal chat template takes ~2 s to render per call on this machine, so a
# 2,500-row dataset spent over an hour in rendering alone. The template does not
# transform message text, so each shape (with or without a system prompt) is rendered
# once with sentinel strings and the real text substituted in. prompt_text_slow is the
# reference; tune/check_prompting (below) asserts the two agree on every row.
_SYS, _REQ = "\x00ASTCSS_SYSTEM\x00", "\x00ASTCSS_REQUEST\x00"
_shapes = {}


def prompt_text_slow(tok, system, request):
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": request}]
    return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)


def prompt_text(tok, system, request):
    key = (id(tok), bool(system))
    if key not in _shapes:
        shape = prompt_text_slow(tok, _SYS if system else None, _REQ)
        ok = shape.count(_REQ) == 1 and (shape.count(_SYS) == 1) == bool(system)
        _shapes[key] = shape if ok else None
    shape = _shapes[key]
    if shape is None or _SYS in (system or "") or _REQ in request:
        return prompt_text_slow(tok, system, request)
    # The Qwen template trims each message's content (`content|trim`): card_v1c.md's
    # trailing newline and any padding on a request never reach the rendered prompt.
    out = shape.replace(_REQ, request.strip())
    return out.replace(_SYS, system.strip()) if system else out


def check(tok, pairs):
    """[(system, request)] -> number of mismatches between the fast and reference renders."""
    return sum(1 for s, r in pairs if prompt_text(tok, s, r) != prompt_text_slow(tok, s, r))


def end_of_turn(tok):
    # Qwen chat templates close every turn with <|im_end|>; fall back to eos elsewhere.
    return "<|im_end|>" if "<|im_end|>" in tok.get_vocab() else tok.eos_token
