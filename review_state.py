"""Testable request lifecycle: navigation invalidates results, selection does not."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewTicket:
    sequence: int
    identifier: str
    item: str
    revision: int


class ReviewState:
    def __init__(self):
        self.sequence = 0
        self.ticket = None
        self.manual_choice = False
        self.phase = 'idle'
        self.report = None

    def begin(self, identifier, item, revision):
        self.sequence += 1
        self.ticket = ReviewTicket(self.sequence, identifier, item, revision)
        self.manual_choice = False
        self.phase, self.report = 'running', None
        return self.ticket

    def select(self):
        # Crucially, a dropdown write does NOT cancel inference or its diagnostics.
        self.manual_choice = True

    def accept(self, ticket, report):
        if ticket != self.ticket:
            return False
        self.phase, self.report = 'ready', report
        return True

    def invalidate(self):
        self.sequence += 1
        self.ticket = None
        self.phase, self.report = 'idle', None

    def can_auto_accept(self, enabled=False, variant=False, pending=True, dirty=False):
        return bool(enabled and not variant and pending and not dirty and not self.manual_choice
                    and self.phase == 'ready' and self.report and self.report.suggestion
                    and self.report.suggestion.automatic)
