"""render — turn (template_id, slots) into the exact line TRON emits.

Every word TRON emits during a session comes from messages.yaml through here
(contracts §0, §6). Two kinds of template:
  - human-facing (terminal / operator / tg / session): inline `text`, rendered as-is.
  - worker-facing (channel: worker): no inline copy — it carries `pmt: PMT-*`, and the
    body is imported fresh from the prompt layer at tick (M-04). The agent prompt is the
    operator's to author; messages.yaml only points at it.
No backend narration ever reaches a human; the LLM's only free-text reaches a human via
the {detail} slot of a canned template.
"""
import util
from prompts import Prompts


class Renderer:
    def __init__(self, ctx):
        self.msgs = util.load_yaml(ctx.messages)
        self.templates = self.msgs.get("templates", {})
        self.prompts = Prompts(ctx)

    def render(self, template_id, slots=None):
        slots = slots or {}
        tpl = self.templates.get(template_id)
        if tpl is None:
            raise KeyError(f"render: no template '{template_id}' in messages.yaml")
        pmt = tpl.get("pmt")
        if pmt:                                  # worker-facing: import the PMT body by id
            return self.prompts.load(pmt, slots)
        try:
            return tpl["text"].format(**slots)
        except KeyError as e:
            raise KeyError(f"render: template '{template_id}' missing slot {e}")

    def channel(self, template_id):
        return self.templates.get(template_id, {}).get("channel")
