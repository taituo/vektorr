from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Label, Digits
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.reactive import reactive
from textual.timer import Timer
import requests
import json
import os
from datetime import datetime

API_URL = "http://localhost:8090"
DECISION_LOG = "decisions.jsonl"

class MatchCell(Static):
    """A single cell in the Matrix representing one match."""
    
    status_style = reactive("idle")
    match_data = reactive({})

    def compose(self) -> ComposeResult:
        with Vertical(classes="cell_container"):
            yield Label("IDLE", id="status_label")
            yield Label("--", id="match_id_label")
            yield Label("0-0 | 0'", id="score_label")
            yield Label("TPS: --", id="tps_label")
            yield Label("xG: --", id="xg_label")

    def watch_match_data(self, data: dict) -> None:
        if not data:
            return
            
        mid = data.get("match_id", "???")
        minute = data.get("minute", 0)
        tps = data.get("tps", "LOW")
        xg = data.get("xg_10m", 0.0)
        can_bet = data.get("can_bet", False)
        reason = data.get("reason", "")
        
        # Update labels
        self.query_one("#match_id_label").update(f"[b]{mid[:15]}[/]")
        self.query_one("#score_label").update(f"Min: {minute}")
        self.query_one("#tps_label").update(f"TPS: {tps}")
        self.query_one("#xg_label").update(f"xG 10m: {xg:.2f}")

        # Visual Logic
        if can_bet:
            self.status_style = "fire"
            self.query_one("#status_label").update("🎯 FIRE! 🎯")
        elif tps == "PRESS":
            self.status_style = "press"
            self.query_one("#status_label").update("⚡ PRESS ⚡")
        elif reason in ["LATENCY_HIGH", "ODDS_LATENCY_HIGH"]:
            self.status_style = "lag"
            self.query_one("#status_label").update("🐢 LAG 🐢")
        else:
            self.status_style = "idle"
            self.query_one("#status_label").update("· IDLE ·")

    def watch_status_style(self, style: str) -> None:
        self.remove_class("fire")
        self.remove_class("press")
        self.remove_class("lag")
        self.remove_class("idle")
        self.add_class(style)

class VektorrMatrix(App):
    """Old-skool Stock Broker Matrix for picking raisins."""

    CSS = """
    Grid {
        grid-size: 4 2;
        grid-gutter: 1;
        padding: 1;
    }

    .cell_container {
        height: 100%;
        content-align: center middle;
        border: tall $primary;
        padding: 1;
    }

    #status_label {
        text-style: bold;
        height: 2;
        content-align: center middle;
    }

    #match_id_label { color: $text-muted; }

    /* STATE COLORS */
    .idle { background: $surface; color: $text-muted; border: tall $surface-lighten-1; }
    
    .press { 
        background: #997700; 
        color: white; 
        border: tall #ffcc00;
    }
    
    .fire { 
        background: #00ff00; 
        color: black; 
        border: double #ffffff;
        text-style: bold;
    }

    .lag { background: #440000; color: #ff0000; border: tall #ff5555; }

    #account_bar {
        height: 5;
        background: $primary-background-darken-2;
        border-top: solid $primary;
        padding: 1 2;
    }

    .header_text { color: $accent; text-style: bold; }
    """

    BINDINGS = [("q", "quit", "Quit"), ("r", "reset", "Reset Logs")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Grid(id="matrix_grid"):
            # Create 8 cells for matches
            for i in range(8):
                yield MatchCell(id=f"match_{i}")
        
        with Horizontal(id="account_bar"):
            with Vertical():
                yield Label("ACCOUNT STATUS", classes="header_text")
                yield Digits("$1000.00", id="balance_digits")
            with Vertical():
                yield Label("SYSTEM STATUS", classes="header_text")
                yield Static("CONNECTED / 51% EDGE READY", id="sys_status")
        yield Footer()

    def on_mount(self) -> None:
        self.last_file_pos = 0
        self.match_to_cell = {} # map match_id to cell index
        self.set_interval(0.5, self.update_from_logs)
        self.set_interval(2.0, self.update_account)

    def update_account(self) -> None:
        try:
            resp = requests.get(f"{API_URL}/summary", timeout=0.2)
            if resp.status_code == 200:
                data = resp.json()
                self.query_one("#balance_digits").update(f"${data['balance']:.2f}")
                pnl = data['total_pnl']
                status = f"ROI: {data['roi_pct']:.1f}% | P&L: {pnl:+.2f} | TRADES: {data['total_trades']}"
                self.query_one("#sys_status").update(status)
        except Exception:
            # Silently fail on connection errors to avoid flickering
            self.query_one("#sys_status").update("[b red]API OFFLINE[/]")

    def update_from_logs(self) -> None:
        if not os.path.exists(DECISION_LOG):
            return

        try:
            with open(DECISION_LOG, "r") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                
                if size < self.last_file_pos:
                    self.last_file_pos = 0 # File rotated
                
                if size == self.last_file_pos:
                    return

                f.seek(self.last_file_pos)
                lines = f.readlines()
                self.last_file_pos = f.tell()

                for line in lines:
                    if not line.strip(): continue
                    try:
                        data = json.loads(line)
                        mid = data.get("match_id")
                        
                        if mid not in self.match_to_cell:
                            # Assign to first empty cell
                            idx = len(self.match_to_cell)
                            if idx < 8:
                                self.match_to_cell[mid] = idx
                            else:
                                continue # Out of cells
                        
                        cell_idx = self.match_to_cell[mid]
                        # Verify widget exists before updating
                        try:
                            cell = self.query_one(f"#match_{cell_idx}")
                            cell.match_data = data
                            if data.get("can_bet"):
                                self.bell()
                        except:
                            pass

                    except json.JSONDecodeError:
                        pass
        except Exception:
            # Catch file IO errors to prevent crash
            pass

    def action_reset(self) -> None:
        if os.path.exists(DECISION_LOG):
            os.remove(DECISION_LOG)
        self.last_file_pos = 0
        for i in range(8):
            self.query_one(f"#match_{i}").match_data = {}

if __name__ == "__main__":
    VektorrMatrix().run()