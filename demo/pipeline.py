"""Tiny plism-like example; never reads or writes external services."""


def normalize_event(event):
    return {"text": event.get("text", "").strip(), "source": "local"}


def build_projection(events):
    return [normalize_event(event) for event in events]


def export_analysis(events):
    return build_projection(events)


class SessionStore:
    def save(self, events):
        return export_analysis(events)

    def preview(self, events):
        return self.save(events)
