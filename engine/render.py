"""render — turn (template_id, slots) into the exact line a human sees.

Every word TRON emits during a session comes from messages.yaml through here
(contracts §0, §6). No backend narration ever reaches a human; the LLM's only
free-text reaches a human via the {detail} slot of a canned template.
"""
import util


class Renderer:
    def __init__(self, ctx):
        self.msgs = util.load_yaml(ctx.messages)
        self.templates = self.msgs.get("templates", {})

    def render(self, template_id, slots=None):
        slots = slots or {}
        tpl = self.templates.get(template_id)
        if tpl is None:
            raise KeyError(f"render: no template '{template_id}' in messages.yaml")
        text = tpl["text"]
        try:
            return text.format(**slots)
        except KeyError as e:
            raise KeyError(f"render: template '{template_id}' missing slot {e}")

    def channel(self, template_id):
        return self.templates.get(template_id, {}).get("channel")
