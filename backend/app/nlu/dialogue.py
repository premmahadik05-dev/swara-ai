"""Stateful dialogue manager: cart, clarification questions, stock validation, confirmation.

Pure logic - no database, no network.  The service layer feeds it fresh product data
(``ProductView``) and persists the returned :class:`DialogState`.  The language model
never writes to inventory: every quantity that reaches the cart passes through
:func:`convert_quantity` and the stock checks below.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from . import nlg
from .lexicon import Lexicon, ProductView
from .parser import ParseResult, ParsedLine, parse_utterance
from .units import VOLUME, WEIGHT, convert_quantity, fmt_qty, is_whole, line_total_paise, quantize_qty

SUGGESTION_MIN = 72.0


# ------------------------------------------------------------------ state
@dataclass
class CartLine:
    product_id: int
    qty: Decimal
    assumed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"product_id": self.product_id, "qty": str(self.qty), "assumed": self.assumed}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "CartLine":
        return CartLine(int(d["product_id"]), Decimal(d["qty"]), bool(d.get("assumed", False)))


@dataclass
class Pending:
    kind: str  # choose_product | need_qty | need_unit | need_pack_count | need_whole | confirm_partial | confirm_suggestion | confirm_unit
    product_id: Optional[int] = None
    options: list[int] = field(default_factory=list)
    qty: Optional[Decimal] = None  # spoken quantity (not yet converted)
    unit: Optional[str] = None  # spoken unit
    suggested: Optional[Decimal] = None  # base-unit quantity to apply on "yes"
    term: Optional[str] = None
    generic: Optional[str] = None
    replace: bool = False
    assumed: bool = False
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "product_id": self.product_id, "options": self.options,
            "qty": None if self.qty is None else str(self.qty), "unit": self.unit,
            "suggested": None if self.suggested is None else str(self.suggested),
            "term": self.term, "generic": self.generic, "replace": self.replace,
            "assumed": self.assumed, "note": self.note,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Pending":
        return Pending(
            kind=d["kind"], product_id=d.get("product_id"), options=list(d.get("options") or []),
            qty=None if d.get("qty") is None else Decimal(d["qty"]), unit=d.get("unit"),
            suggested=None if d.get("suggested") is None else Decimal(d["suggested"]),
            term=d.get("term"), generic=d.get("generic"), replace=bool(d.get("replace")),
            assumed=bool(d.get("assumed")), note=d.get("note"),
        )


@dataclass
class DialogState:
    phase: str = "collecting"  # collecting | confirming | completed | cancelled
    awaiting: Optional[str] = None  # more_items | confirm_order
    cart: list[CartLine] = field(default_factory=list)
    queue: list[Pending] = field(default_factory=list)
    language: str = "en"
    order_id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase, "awaiting": self.awaiting, "language": self.language, "order_id": self.order_id,
            "cart": [c.to_dict() for c in self.cart], "queue": [p.to_dict() for p in self.queue],
        }

    @staticmethod
    def from_dict(d: Optional[dict[str, Any]]) -> "DialogState":
        if not d:
            return DialogState()
        return DialogState(
            phase=d.get("phase", "collecting"), awaiting=d.get("awaiting"), language=d.get("language", "en"),
            order_id=d.get("order_id"),
            cart=[CartLine.from_dict(c) for c in d.get("cart", [])],
            queue=[Pending.from_dict(p) for p in d.get("queue", [])],
        )


@dataclass
class Outcome:
    reply: str
    reply_lang: str
    state: DialogState
    parse: ParseResult
    events: list[dict[str, Any]]
    commit: bool = False  # service should create the order now


# ------------------------------------------------------------------ helpers
def cart_view(state: DialogState, products: dict[int, ProductView], lang: str = "en") -> dict[str, Any]:
    lines = []
    total = 0
    for c in state.cart:
        p = products.get(c.product_id)
        if not p:
            continue
        lt = line_total_paise(p.price_paise, c.qty)
        total += lt
        lines.append({
            "product_id": p.id, "sku": p.sku, "name_en": p.name_en, "name_gu": p.name_gu, "name_hi": p.name_hi,
            "names": {lang: v[0] for lang, v in p.names.items() if v},  # the name in each other language that has one (mr, bn, ta, ...), for the bill
            "qty": str(c.qty), "unit": p.unit, "unit_price_paise": p.price_paise, "line_total_paise": lt,
            "assumed": c.assumed, "in_stock": p.stock,
        })
    return {"lines": lines, "total_paise": total}


def cart_total(state: DialogState, products: dict[int, ProductView]) -> int:
    return sum(line_total_paise(products[c.product_id].price_paise, c.qty) for c in state.cart if c.product_id in products)


class DialogueManager:
    def __init__(self, lexicon: Lexicon):
        self.lex = lexicon

    # ---------------------------------------------------------------- formatting
    def _name(self, p: ProductView, lang: str) -> str:
        return p.display_name(lang)

    def _item(self, p: ProductView, qty: Decimal, lang: str) -> str:
        return nlg.item_text(lang, self._name(p, lang), qty, p.unit)

    def _items(self, pairs: list[tuple[ProductView, Decimal]], lang: str) -> str:
        return nlg.join_items(lang, [self._item(p, q, lang) for p, q in pairs])

    def _pack_text(self, p: ProductView, lang: str) -> str:
        if p.pack_size is None or p.pack_size_unit is None:
            return ""
        if p.pack_size_unit == "kg" and p.pack_size < 1:
            return f"{fmt_qty(p.pack_size * 1000)} {nlg.unit_label(lang, 'g')}"
        return f"{fmt_qty(p.pack_size)} {nlg.unit_label(lang, p.pack_size_unit)}"

    # ---------------------------------------------------------------- main entry
    def handle(
        self, text: str, state: DialogState, products: dict[int, ProductView], keep_language: bool = False,
        language_hint: Optional[str] = None,
    ) -> Outcome:
        """`keep_language` is for button presses that send a fixed English command ("confirm"): they say nothing about the
        language the customer is speaking, so they must not switch the conversation (or the saved order) to English."""
        parse = parse_utterance(text, self.lex, cart_has_items=bool(state.cart), language_hint=language_hint)
        if parse.lang_confident and not keep_language:
            state.language = parse.language
        lang = state.language
        events: list[dict[str, Any]] = []
        cues = parse.cues

        if state.phase in ("completed", "cancelled"):
            state = DialogState(language=lang)
        # drop cart lines whose product has disappeared
        state.cart = [c for c in state.cart if c.product_id in products]

        had_queue = bool(state.queue)
        consumed = False
        used: set[int] = set()
        if state.queue:
            consumed, used = self._resolve_pending(parse, state, products, events)

        # explicit cancel of the whole order (no product mentioned)
        if "cancel" in cues and not any(ln.product_ids for ln in parse.lines):
            state.cart.clear()
            state.queue.clear()
            state.phase, state.awaiting = "cancelled", None
            return Outcome(nlg.render("cancelled", lang), lang, state, parse, events)

        intent = parse.intent
        commit = False
        reply_parts: list[str] = []
        new_lines = [ln for ln in parse.lines if id(ln) not in used and not self._is_answer_line(ln)]

        if intent in ("add", "set") and new_lines:
            for ln in new_lines:
                self._process_line(ln, state, products, events, replace=(intent == "set"))
            if state.phase != "confirming":
                state.awaiting = "more_items"
        elif intent == "remove" and new_lines:
            for ln in new_lines:
                self._remove(ln, state, products, events)
        elif intent == "query" and new_lines:
            self._query(parse, new_lines, state, products, events)
        elif not consumed:
            res = self._dispatch_cue(parse, state, products, events)
            if res == "COMMIT":
                commit = True
            elif res:
                reply_parts.append(res)

        if commit:
            return Outcome("", lang, state, parse, events, commit=True)

        if not reply_parts:
            reply_parts.append(self._compose_reply(state, products, events, lang, had_queue and not consumed, parse))
        return Outcome(" ".join(p for p in reply_parts if p), lang, state, parse, events)

    @staticmethod
    def _is_answer_line(ln: ParsedLine) -> bool:
        """A line with a quantity but no product is only an answer to a pending question."""
        return not ln.product_ids and ln.unknown_term is None

    # ---------------------------------------------------------------- cue dispatch
    def _dispatch_cue(self, parse: ParseResult, state: DialogState, products: dict[int, ProductView], events: list) -> Optional[str]:
        cues = parse.cues
        lang = state.language
        if state.queue:
            return None  # a question is open; compose_reply re-asks it
        if "greeting" in cues and "confirm" not in cues and "done" not in cues:
            return nlg.render("greeting", lang)
        if state.phase == "confirming":
            if "confirm" in cues and "deny" not in cues:
                return "COMMIT" if state.cart else nlg.render("cart_empty", lang)
            if "deny" in cues:
                state.phase, state.awaiting = "collecting", None
                return nlg.render("no_problem_change", lang)
            if "done" in cues:
                return self._summary_text(state, products, lang)
            return None
        # collecting
        if "done" in cues:
            return self._to_summary(state, products)
        if "confirm" in cues:
            if state.awaiting == "more_items":
                state.awaiting = None
                return nlg.render("what_else", lang)
            return self._to_summary(state, products)
        if "deny" in cues:
            if not state.cart:
                return nlg.render("cart_empty", lang)
            return self._to_summary(state, products)
        return None

    def _to_summary(self, state: DialogState, products: dict[int, ProductView]) -> str:
        lang = state.language
        if not state.cart:
            return nlg.render("cart_empty", lang)
        state.phase, state.awaiting = "confirming", "confirm_order"
        return self._summary_text(state, products, lang)

    def _summary_text(self, state: DialogState, products: dict[int, ProductView], lang: str) -> str:
        pairs = [(products[c.product_id], c.qty) for c in state.cart if c.product_id in products]
        total = nlg.money(cart_total(state, products))
        return nlg.render("confirm_summary", lang, items=self._items(pairs, lang), total=total)

    # ---------------------------------------------------------------- line processing
    def _process_line(self, ln: ParsedLine, state: DialogState, products: dict[int, ProductView], events: list, replace: bool = False) -> None:
        if not ln.product_ids:
            term = ln.unknown_term or ""
            sug = self.lex.suggest(term.split()) if term else []
            if sug and sug[0][1] >= SUGGESTION_MIN and sug[0][0] in products:
                state.queue.append(Pending("confirm_suggestion", product_id=sug[0][0], term=term, qty=ln.qty, unit=ln.unit, replace=replace))
            else:
                events.append({"type": "unknown", "term": term})
            return
        if len(ln.product_ids) > 1:
            opts = [i for i in ln.product_ids if i in products]
            if len(opts) == 1:
                ln.product_ids = opts
            else:
                state.queue.append(Pending("choose_product", options=opts, qty=ln.qty, unit=ln.unit, generic=ln.spoken, replace=replace))
                return
        p = products.get(ln.product_ids[0])
        if p is None:
            return
        self._qty_stage(p, ln.qty, ln.unit, ln.qty_ambiguous, ln.assumed_default, replace, state, events)

    def _qty_stage(
        self, p: ProductView, qty: Optional[Decimal], unit: Optional[str], ambiguous: bool, assumed: bool,
        replace: bool, state: DialogState, events: list,
    ) -> None:
        if ambiguous or qty is None:
            state.queue.append(Pending("need_qty", product_id=p.id, assumed=assumed, replace=replace))
            return
        conv = convert_quantity(p.unit, p.pack_size, p.pack_size_unit, qty, unit)
        if conv.status == "need_unit":
            state.queue.append(Pending("need_unit", product_id=p.id, qty=qty, assumed=assumed, replace=replace))
            return
        if conv.status == "non_integer":
            if conv.hint and conv.hint.startswith("pack_size"):
                state.queue.append(Pending("need_pack_count", product_id=p.id, assumed=assumed, replace=replace))
            else:
                state.queue.append(Pending("need_whole", product_id=p.id, assumed=assumed, replace=replace))
            return
        if conv.status == "mismatch":
            # kilo <-> litre confusion is very common for oil/milk: offer the same number in the right unit
            if p.unit in ("kg", "l") and unit in (*WEIGHT, *VOLUME):
                num = qty * (WEIGHT.get(unit) or VOLUME.get(unit) or Decimal(1))
                state.queue.append(Pending("confirm_unit", product_id=p.id, suggested=quantize_qty(num), assumed=assumed, replace=replace))
            else:
                state.queue.append(Pending("unit_wrong", product_id=p.id, assumed=assumed, replace=replace))
            return
        assert conv.qty is not None
        self._add_to_cart(p, conv.qty, assumed, replace, state, events)

    def _add_to_cart(self, p: ProductView, qty: Decimal, assumed: bool, replace: bool, state: DialogState, events: list) -> None:
        existing = next((c for c in state.cart if c.product_id == p.id), None)
        have = existing.qty if existing else Decimal(0)
        target = qty if replace else have + qty
        if p.stock <= 0:
            events.append({"type": "out_of_stock", "product_id": p.id})
            return
        if target > p.stock:
            avail = p.stock - (Decimal(0) if replace else have)
            if p.unit in ("pack", "pc"):
                avail = Decimal(math.floor(avail))
            if avail <= 0:
                events.append({"type": "no_more_stock", "product_id": p.id})
                return
            state.queue.append(Pending("confirm_partial", product_id=p.id, suggested=quantize_qty(avail), replace=replace, assumed=assumed))
            return
        if existing:
            existing.qty = quantize_qty(target)
            existing.assumed = existing.assumed or assumed
            events.append({"type": "updated" if replace else "added", "product_id": p.id, "qty": str(qty), "assumed": assumed})
        else:
            state.cart.append(CartLine(p.id, quantize_qty(target), assumed))
            events.append({"type": "added", "product_id": p.id, "qty": str(qty), "assumed": assumed})
        if state.phase == "confirming":
            state.awaiting = "confirm_order"

    def _remove(self, ln: ParsedLine, state: DialogState, products: dict[int, ProductView], events: list) -> None:
        for pid in ln.product_ids:
            idx = next((i for i, c in enumerate(state.cart) if c.product_id == pid), None)
            if idx is None:
                events.append({"type": "not_in_cart", "product_id": pid})
            else:
                state.cart.pop(idx)
                events.append({"type": "removed", "product_id": pid})

    def _query(self, parse: ParseResult, lines: list[ParsedLine], state: DialogState, products: dict[int, ProductView], events: list) -> None:
        for ln in lines:
            if len(ln.product_ids) != 1 or ln.product_ids[0] not in products:
                continue
            p = products[ln.product_ids[0]]
            ev: dict[str, Any] = {"type": "price", "product_id": p.id, "in_stock": p.stock > 0}
            if ln.qty is not None and not ln.qty_ambiguous:
                conv = convert_quantity(p.unit, p.pack_size, p.pack_size_unit, ln.qty, ln.unit or (p.unit if p.unit in ("pack", "pc") else None))
                if conv.status == "ok" and conv.qty is not None:
                    ev["qty"] = str(conv.qty)
                    ev["total_paise"] = line_total_paise(p.price_paise, conv.qty)
            events.append(ev)

    # ---------------------------------------------------------------- pending resolution
    def _resolve_pending(self, parse: ParseResult, state: DialogState, products: dict[int, ProductView], events: list) -> tuple[bool, set[int]]:
        pend = state.queue[0]
        cues = parse.cues
        lines = parse.lines
        none: tuple[bool, set[int]] = (False, set())
        qty_line = next((ln for ln in lines if not ln.product_ids and ln.qty is not None and not ln.qty_ambiguous), None)
        if "cancel" in cues and not any(ln.product_ids for ln in lines):
            return none  # whole-order cancel is handled by the caller
        yes = "confirm" in cues
        no = "deny" in cues or "remove" in cues
        used_q = {id(qty_line)} if qty_line is not None else set()

        if pend.kind in ("confirm_partial", "confirm_unit", "confirm_suggestion"):
            if qty_line is not None and pend.product_id in products:
                state.queue.pop(0)
                self._qty_stage(products[pend.product_id], qty_line.qty, qty_line.unit, False, pend.assumed, pend.replace, state, events)
                return True, used_q
            if yes and not no:
                state.queue.pop(0)
                p = products.get(pend.product_id or -1)
                if p is not None:
                    if pend.kind == "confirm_suggestion":
                        self._qty_stage(p, pend.qty, pend.unit, False, False, pend.replace, state, events)
                    else:
                        assert pend.suggested is not None
                        self._add_to_cart(p, pend.suggested, pend.assumed, pend.replace, state, events)
                return True, set()
            if no and not yes:
                state.queue.pop(0)
                events.append({"type": "skipped"})
                return True, set()
            return none

        if pend.kind == "choose_product":
            pick, pick_line = None, None
            for ln in lines:
                hit = next((pid for pid in ln.product_ids if pid in pend.options), None)
                if hit is not None:
                    pick, pick_line = hit, ln
                    break
            if pick is None:
                # last resort: loose match of the answer text against the offered options only
                sug = self.lex.suggest(parse.tokens, limit=len(pend.options) + 3, cutoff=70.0)
                pick = next((pid for pid, _ in sug if pid in pend.options), None)
            if pick is not None and pick in products:
                state.queue.pop(0)
                q = qty_line.qty if qty_line is not None else (pick_line.qty if pick_line is not None and pick_line.qty is not None else pend.qty)
                u = qty_line.unit if qty_line is not None else (pick_line.unit if pick_line is not None and pick_line.qty is not None else pend.unit)
                self._qty_stage(products[pick], q, u, False, False, pend.replace, state, events)
                used = set(used_q)
                if pick_line is not None:
                    used.add(id(pick_line))
                else:
                    used.update(id(ln) for ln in lines)  # loosely matched answer: nothing else to process
                return True, used
            if no and not yes:
                state.queue.pop(0)
                events.append({"type": "skipped"})
                return True, set()
            return none

        # need_qty / need_unit / need_pack_count / need_whole / unit_wrong
        p = products.get(pend.product_id or -1)
        if qty_line is not None and p is not None:
            state.queue.pop(0)
            unit = qty_line.unit
            if unit is None and p.unit in ("kg", "l") and pend.kind != "need_pack_count":
                unit = p.unit  # we just asked "how many kg?" so a bare number means that unit
            self._qty_stage(p, qty_line.qty, unit, False, pend.assumed, pend.replace, state, events)
            return True, used_q
        if no and not yes:
            state.queue.pop(0)
            events.append({"type": "skipped"})
            return True, set()
        return none

    # ---------------------------------------------------------------- reply composition
    def _ask(self, pend: Pending, products: dict[int, ProductView], lang: str) -> str:
        p = products.get(pend.product_id) if pend.product_id else None
        if pend.kind == "choose_product":
            opts = nlg.join_items(lang, [self._name(products[i], lang) for i in pend.options if i in products])
            return nlg.render("choose_product", lang, generic=pend.generic or "", options=opts)
        if pend.kind == "confirm_suggestion" and p:
            return nlg.render("confirm_suggestion", lang, term=pend.term or "", product=self._name(p, lang))
        if p is None:
            return nlg.render("didnt_understand", lang)
        name = self._name(p, lang)
        if pend.kind == "need_qty":
            return nlg.render("need_qty", lang, product=name)
        if pend.kind in ("need_unit", "unit_wrong"):
            key = "need_unit" if pend.kind == "need_unit" else "unit_wrong"
            return nlg.render(key, lang, product=name, unit=nlg.unit_label(lang, p.unit, Decimal(2)))
        if pend.kind == "need_pack_count":
            return nlg.render("need_pack_count", lang, product=name, pack=self._pack_text(p, lang))
        if pend.kind == "need_whole":
            return nlg.render("need_whole", lang, product=name, unit=nlg.unit_label(lang, p.unit, Decimal(2)))
        if pend.kind == "confirm_unit":
            q = pend.suggested or Decimal(1)
            return nlg.render("confirm_unit", lang, product=name, qty=fmt_qty(q), unit=nlg.unit_label(lang, p.unit, q))
        if pend.kind == "confirm_partial":
            q = pend.suggested or Decimal(0)
            return nlg.render("confirm_partial", lang, product=name, avail=f"{fmt_qty(q)} {nlg.unit_label(lang, p.unit, q)}")
        return nlg.render("didnt_understand", lang)

    def _compose_reply(
        self, state: DialogState, products: dict[int, ProductView], events: list[dict[str, Any]], lang: str,
        reasked: bool, parse: ParseResult,
    ) -> str:
        parts: list[str] = []
        added = [(products[e["product_id"]], Decimal(e["qty"])) for e in events if e["type"] == "added" and e["product_id"] in products]
        updated = [(products[e["product_id"]], Decimal(e["qty"])) for e in events if e["type"] == "updated" and e["product_id"] in products]
        removed = [self._name(products[e["product_id"]], lang) for e in events if e["type"] == "removed" and e["product_id"] in products]
        assumed = [products[e["product_id"]] for e in events if e["type"] in ("added", "updated") and e.get("assumed") and e["product_id"] in products]
        has_queue = bool(state.queue)

        if added:
            key = "added_only" if has_queue or state.phase == "confirming" else "added"
            parts.append(nlg.render(key, lang, items=self._items(added, lang), total=nlg.money(cart_total(state, products))))
        if updated:
            parts.append(nlg.render("updated", lang, items=self._items(updated, lang)))
        for p in assumed[:1]:
            parts.append(nlg.render("assumed", lang, product=self._name(p, lang)))
        if removed:
            parts.append(nlg.render("removed", lang, items=nlg.join_items(lang, removed)))
        for e in events:
            t = e["type"]
            if t == "out_of_stock" and e["product_id"] in products:
                parts.append(nlg.render("out_of_stock", lang, product=self._name(products[e["product_id"]], lang)))
            elif t == "no_more_stock" and e["product_id"] in products:
                parts.append(nlg.render("no_more_stock", lang, product=self._name(products[e["product_id"]], lang)))
            elif t == "not_in_cart" and e["product_id"] in products:
                parts.append(nlg.render("not_in_cart", lang, product=self._name(products[e["product_id"]], lang)))
            elif t == "unknown":
                parts.append(nlg.render("unknown", lang, term=e["term"]))
            elif t == "skipped":
                parts.append(nlg.render("skipped", lang))
            elif t == "price":
                p = products[e["product_id"]]
                if "total_paise" in e:
                    parts.append(nlg.render("price_qty", lang, items=self._item(p, Decimal(e["qty"]), lang), total=nlg.money(e["total_paise"])))
                else:
                    parts.append(nlg.render("price_one", lang, product=self._name(p, lang), price=nlg.money(p.price_paise), unit=nlg.unit_label(lang, p.unit)))
                if not e["in_stock"]:
                    parts.append(nlg.render("price_oos", lang))

        if has_queue:
            parts.append(self._ask(state.queue[0], products, lang))
        elif state.phase == "confirming" and (added or updated or removed):
            if state.cart:
                parts.append(self._summary_text(state, products, lang))
            else:
                state.phase, state.awaiting = "collecting", None
                parts.append(nlg.render("cart_empty", lang))
        elif not parts:
            if state.phase == "confirming" and state.cart:
                parts.append(self._summary_text(state, products, lang))
            else:
                parts.append(nlg.render("didnt_understand", lang))
        elif removed and state.phase == "collecting" and not state.cart:
            parts.append(nlg.render("cart_empty", lang))
        return " ".join(parts)

    # ---------------------------------------------------------------- order lifecycle (called by service)
    def after_commit(self, state: DialogState, order_id: int, total_paise: int, products: dict[int, ProductView]) -> str:
        lang = state.language
        state.phase, state.awaiting, state.order_id = "completed", None, order_id
        return nlg.render("confirmed", lang, num=order_id, total=nlg.money(total_paise))

    def after_commit_failed(self, state: DialogState, shortages: dict[int, Decimal], products: dict[int, ProductView]) -> str:
        """Stock changed between the readback and the commit: shrink the cart and ask again."""
        lang = state.language
        adjusted: list[tuple[ProductView, Decimal]] = []
        for c in list(state.cart):
            if c.product_id in shortages:
                avail = shortages[c.product_id]
                p = products.get(c.product_id)
                if p and p.unit in ("pack", "pc"):
                    avail = Decimal(math.floor(avail))
                if avail <= 0:
                    state.cart.remove(c)
                else:
                    c.qty = quantize_qty(avail)
                    if p:
                        adjusted.append((p, c.qty))
        state.phase, state.awaiting = "confirming", "confirm_order"
        head = nlg.render("stock_changed", lang, items=self._items(adjusted, lang) if adjusted else "-")
        return f"{head} {self._summary_text(state, products, lang)}" if state.cart else f"{head} {nlg.render('cart_empty', lang)}"
