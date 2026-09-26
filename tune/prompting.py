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


_trims = {}


def _template_trims(tok):
    """Does this tokenizer's chat template trim message content? Measured, not assumed:
    Qwen3.5's template applies `content|trim` (card_v1c.md's trailing newline never reaches
    the prompt); Qwen3-4B-Instruct-2507's keeps content as given."""
    key = id(tok)
    if key not in _trims:
        padded = prompt_text_slow(tok, None, " \n" + _REQ + " \n")
        _trims[key] = (" \n" + _REQ + " \n") not in padded
    return _trims[key]


def prompt_text(tok, system, request):
    key = (id(tok), bool(system))
    if key not in _shapes:
        shape = prompt_text_slow(tok, _SYS if system else None, _REQ)
        ok = shape.count(_REQ) == 1 and (shape.count(_SYS) == 1) == bool(system)
        _shapes[key] = shape if ok else None
    shape = _shapes[key]
    if shape is None or _SYS in (system or "") or _REQ in request:
        return prompt_text_slow(tok, system, request)
    trim = _template_trims(tok)
    out = shape.replace(_REQ, request.strip() if trim else request)
    return out.replace(_SYS, (system.strip() if trim else system)) if system else out


def check(tok, pairs):
    """[(system, request)] -> number of mismatches between the fast and reference renders."""
    return sum(1 for s, r in pairs if prompt_text(tok, s, r) != prompt_text_slow(tok, s, r))


def tag_request(lang, request):
    """The request with its language named, for prompts without a card. Stage 6: a
    no-card adapter trained on nine languages answered Python requests with Java node
    types (`catch_clause`), JavaScript calls (`.call#log`) and Rust names (`.fn#new`),
    because nothing in the prompt said which language. sitting_duck's language
    classifier can supply `lang` at serving time. Training and generation both call this."""
    return "[%s] %s" % (lang, request) if lang else request


_eot = {}


_ANS = "\x00ASTCSS_ANSWER\x00"


def end_of_turn(tok):
    """The token this tokenizer's template puts AFTER an assistant turn.

    Derived from the template rather than guessed, because guessing was wrong. The first
    version returned `<|im_end|>` when that was in the vocabulary and `tok.eos_token`
    otherwise. On Qwen that is correct. On Gemma-3 it is not: turns close with
    `<end_of_turn>` (id 106) while `eos_token` is `<eos>` (id 1), so training appended a
    terminator the template never uses -- the model learns to end its answer with a token
    that does not end a turn. That is train/inference drift of exactly the kind this module
    exists to prevent, and it is silent.

    So: render a real assistant turn with a sentinel answer and read off whatever the
    template appends. Falls back to the old behaviour only if the sentinel does not survive
    (a template that transforms content), which no template we have met does.

    Cached: rendering a template costs ~2 s on some tokenizers and get_vocab() rebuilds a
    248k-entry dict, neither of which belongs in a per-row path.
    """
    key = id(tok)
    if key not in _eot:
        tail = None
        try:
            rendered = tok.apply_chat_template(
                [{"role": "user", "content": "x"}, {"role": "assistant", "content": _ANS}],
                tokenize=False)
            after = rendered.split(_ANS)[-1].strip() if _ANS in rendered else ""
            # The template may append several specials; the terminator is the first one.
            if after.startswith("<"):
                tail = after[:after.index(">") + 1]
        except Exception:                       # no chat template, or it rejects the shape
            tail = None
        if not tail or tail not in tok.get_vocab():
            tail = "<|im_end|>" if "<|im_end|>" in tok.get_vocab() else tok.eos_token
        _eot[key] = tail
    return _eot[key]
