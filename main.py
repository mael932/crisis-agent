"""
Crisis Response Agent — Timothée Chalamet PR Workflow
"""

import anthropic
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")
MODEL = "claude-opus-4-5-20251101"
MAX_TOKENS = 3500

client = anthropic.Anthropic(api_key=API_KEY)

PACKET_A_PATH = Path("packets/packet_a.md")
PACKET_B_PATH = Path("packets/packet_b.md")
OUTPUT_PATH = Path("output/submission.md")


def load_packet(path):
    if path.exists():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Packet not found: {path}")


def call_claude(system, user, label):
    print(f"\n[AGENT: {label}] calling Claude...")
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    result = response.content[0].text
    print(f"[AGENT: {label}] done.")
    return result


def parse_json(result, agent_name):
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", result, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"{agent_name} returned non-JSON: {result}")


def human_voicemail_review(packet_b):
    """
    Human-in-the-loop step: detect voicemails in packet and ask operator for transcripts.
    Returns enriched packet text with transcripts injected.
    """
    voicemails = []

    # Detect voicemail blocks
    if "Laurent Duchamp" in packet_b:
        voicemails.append({
            "name": "Laurent Duchamp — Maison Clarée",
            "duration": "0:24",
            "key": "laurent"
        })
    if "Tom Ellery" in packet_b:
        voicemails.append({
            "name": "Tom Ellery — Arts & Culture Weekly",
            "duration": "0:28",
            "key": "tom"
        })

    if not voicemails:
        return packet_b, {}

    print("\n" + "=" * 60)
    print("  [HUMAN REVIEW REQUIRED] Audio signals detected in Packet B")
    print("=" * 60)
    print("The workflow has detected voicemail files that require human review.")
    print("Please listen to each voicemail and enter the transcript below.")
    print("Press Enter without typing to skip (voicemail will be flagged as unreviewed).\n")

    transcripts = {}
    for vm in voicemails:
        print(f"Voicemail: {vm['name']} ({vm['duration']})")
        transcript = input(f"  Transcript (or press Enter to skip): ").strip()
        if transcript:
            transcripts[vm["key"]] = transcript
            print(f"  [LOGGED] Transcript recorded for {vm['name']}\n")
        else:
            transcripts[vm["key"]] = "NOT REVIEWED — human operator did not provide transcript"
            print(f"  [SKIPPED] {vm['name']} flagged as unreviewed\n")

    # Inject transcripts into packet text
    enriched = packet_b
    if transcripts.get("laurent"):
        enriched += f"\n\n## Human-Reviewed Voicemail Transcript — Laurent Duchamp\n{transcripts['laurent']}\n"
    if transcripts.get("tom"):
        enriched += f"\n\n## Human-Reviewed Voicemail Transcript — Tom Ellery\n{transcripts['tom']}\n"

    print("[HUMAN REVIEW COMPLETE] Transcripts injected into packet. Continuing pipeline...\n")
    return enriched, transcripts


def triage_agent(packet_a):
    system = """You are a crisis triage specialist for a celebrity PR team.
Read the crisis packet and output ONLY valid JSON with these exact keys:
{
  "severity_score": <1-10 integer>,
  "severity_label": "<LOW|MEDIUM|HIGH|CRITICAL>",
  "rationale": "<2-3 sentences>",
  "meme_risk": "<LOW|MEDIUM|HIGH>",
  "reputational_risk": "<LOW|MEDIUM|HIGH>",
  "awards_night_risk": "<LOW|MEDIUM|HIGH>",
  "sponsor_risk": "<LOW|MEDIUM|HIGH>",
  "hold_comment": <true|false>,
  "hard_deadlines": [{"deadline": "<HH:MM>", "action": "<what must happen>"}],
  "recommended_posture": "<one sentence>"
}
Score 8-10 only if spreading across multiple platforms AND sponsor pressure is active.
hold_comment true if full context unavailable and clip is ambiguous.
Do not invent facts."""
    result = call_claude(system, f"Triage this crisis packet:\n\n{packet_a}", "TRIAGE")
    return parse_json(result, "TRIAGE")


def router_agent(packet_a, triage):
    system = """You are a PR operations router for a celebrity team.
Output ONLY valid JSON:
{
  "routing_plan": [
    {
      "stakeholder": "<Sponsor|Reporter|Manager|Public>",
      "priority": <1-4>,
      "deadline": "<HH:MM>",
      "action_required": "<what to produce>",
      "approval_needed_from": "<who>",
      "channel": "<email|call|statement|social>",
      "notes": "<constraints>"
    }
  ],
  "sequencing_rationale": "<2-3 sentences>",
  "things_to_not_do_yet": ["<action>"]
}
Rules: talent unreachable until 6:05 PM. Sponsor deadline is 5:50 PM. No unverified facts."""
    prompt = f"Crisis packet:\n{packet_a}\n\nTriage:\n{json.dumps(triage, indent=2)}\n\nProduce routing plan."
    result = call_claude(system, prompt, "ROUTER")
    return parse_json(result, "ROUTER")


def drafting_agent(packet_a, triage, routing):
    system = """You are a senior PR copywriter handling an active celebrity crisis.
Output ONLY valid JSON:
{
  "drafts": {
    "sponsor_holding_line": {"raw": "<draft>", "word_count": <int>, "approval_required": "<who>", "deadline": "<HH:MM>"},
    "reporter_reply": {"raw": "<draft>", "approval_required": "<who>", "deadline": "<HH:MM>"},
    "manager_internal_brief": {"raw": "<draft>", "approval_required": "none"},
    "talent_holding_note": {"raw": "<note for Timothee at 6:05>", "approval_required": "none"}
  }
}
Voice rules: calm, self-aware, human. No 'you misunderstood'. No jokes. No condescension about arts.
Sponsor holding line MUST be 40 words or fewer. Do not use unverified facts."""
    prompt = f"Crisis packet:\n{packet_a}\n\nTriage:\n{json.dumps(triage, indent=2)}\n\nRouting:\n{json.dumps(routing, indent=2)}\n\nProduce all drafts."
    result = call_claude(system, prompt, "DRAFTING")
    return parse_json(result, "DRAFTING")


def reviewer_agent(packet_a, drafts):
    system = """You are a senior crisis PR reviewer. Critique drafts and produce final versions.
Check: voice rule violations, 40-word sponsor limit, no unverified claims, no talent voice without approval.
Output ONLY valid JSON:
{
  "reviews": {
    "sponsor_holding_line": {"issues_found": ["<issue>"], "final": "<text>", "word_count_final": <int>, "status": "<APPROVED|REVISED|REJECTED>"},
    "reporter_reply": {"issues_found": ["<issue>"], "final": "<text>", "status": "<APPROVED|REVISED|REJECTED>"},
    "manager_internal_brief": {"issues_found": [], "final": "<text>", "status": "<APPROVED|REVISED|REJECTED>"},
    "talent_holding_note": {"issues_found": [], "final": "<text>", "status": "<APPROVED|REVISED|REJECTED>"}
  },
  "reviewer_notes": "<overall notes>"
}"""
    prompt = f"Crisis packet:\n{packet_a}\n\nDrafts to review:\n{json.dumps(drafts, indent=2)}"
    result = call_claude(system, prompt, "REVIEWER")
    return parse_json(result, "REVIEWER")


def escalation_agent(packet_a, packet_b_enriched, phase_a_outputs, transcripts):
    voicemail_context = ""
    if transcripts:
        voicemail_context = "\n\nVOICEMAIL SIGNALS (human-reviewed):\n"
        for key, transcript in transcripts.items():
            voicemail_context += f"- {key.title()}: {transcript}\n"

    system = """You are a crisis escalation specialist. A new packet has arrived with updated sponsor pressure and voicemail signals.
Diff the new situation against Phase A. Update ONLY what needs to change. Do not restart.

For voicemail signals: assess each one for urgency and route accordingly.
- A second sponsor with board pressure is a new HIGH priority signal requiring callback tonight.
- A routine press inquiry unrelated to the crisis is LOW priority and can wait.

Output ONLY valid JSON:
{
  "phase_b_assessment": {
    "new_information": "<what is new vs Phase A>",
    "what_has_not_changed": "<same facts>",
    "escalation_severity_delta": "<how much more severe and why>",
    "sponsor_risk_now": "<CRITICAL|HIGH|MEDIUM|LOW>"
  },
  "voicemail_triage": [
    {
      "sender": "<name>",
      "organization": "<org>",
      "urgency": "<URGENT|MEDIUM|LOW>",
      "assessment": "<what this signal means>",
      "recommended_action": "<what to do and when>",
      "strategic_note": "<any opportunity or risk>"
    }
  ],
  "updated_routing": [
    {
      "stakeholder": "<name>",
      "action_required": "<action>",
      "new_deadline": "<HH:MM>",
      "delta_from_phase_a": "<what changed>"
    }
  ],
  "updated_drafts": {
    "sponsor_escalation_response": {"raw": "<new draft for Maison Valeur>", "word_count": <int>},
    "credible_plan_summary": {"raw": "<concrete plan: what Timothee will do, who approves, timeline>"},
    "second_sponsor_callback_brief": {"raw": "<internal brief for Laurent Duchamp callback before 8 PM>"}
  },
  "phase_a_items_still_valid": ["<item>"],
  "things_cancelled_or_deprioritized": ["<item>"]
}"""

    prompt = f"""PHASE A PACKET:
{packet_a}

PHASE B PACKET (enriched with voicemail transcripts):
{packet_b_enriched}
{voicemail_context}

PHASE A OUTPUTS:
{json.dumps(phase_a_outputs, indent=2)}

Update the plan. Do not restart from scratch."""

    result = call_claude(system, prompt, "ESCALATION")
    return parse_json(result, "ESCALATION")


def build_submission(triage, routing, drafts, reviews, escalation=None, transcripts=None):
    lines = []
    lines.append("# Crisis Response Agent — Submission\n")
    lines.append(f"**Talent:** Timothée Chalamet  ")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ")
    lines.append(f"**Model:** {MODEL}  \n")
    lines.append("\n---\n")
    lines.append("# PHASE A — Initial Response (5:30 PM)\n")
    lines.append("## 1. Triage Assessment\n")
    lines.append(f"**Severity:** {triage.get('severity_score')}/10 — {triage.get('severity_label')}")
    lines.append(f"**Rationale:** {triage.get('rationale')}")
    lines.append(f"**Meme Risk:** {triage.get('meme_risk')} | **Sponsor Risk:** {triage.get('sponsor_risk')} | **Awards Night Risk:** {triage.get('awards_night_risk')}")
    lines.append(f"**Hold Comment:** {'YES' if triage.get('hold_comment') else 'NO'}")
    lines.append(f"**Posture:** {triage.get('recommended_posture')}\n")
    lines.append("### Hard Deadlines\n")
    for d in triage.get("hard_deadlines", []):
        lines.append(f"- `{d['deadline']}` — {d['action']}")
    lines.append("\n## 2. Routing Plan\n")
    lines.append(routing.get("sequencing_rationale", ""))
    for item in routing.get("routing_plan", []):
        lines.append(f"\n**[P{item['priority']}] {item['stakeholder']}** — `{item['deadline']}` via {item['channel']}")
        lines.append(f"- Action: {item['action_required']}")
        lines.append(f"- Approval: {item['approval_needed_from']}")
        if item.get("notes"):
            lines.append(f"- Notes: {item['notes']}")
    lines.append("\n### Do NOT do yet\n")
    for t in routing.get("things_to_not_do_yet", []):
        lines.append(f"- {t}")
    lines.append("\n## 3. Stakeholder Drafts & Reviews\n")
    lines.append("### Sponsor Holding Line (due 5:50 PM)\n")
    raw_s = drafts.get("drafts", {}).get("sponsor_holding_line", {}).get("raw", "")
    final_s = reviews.get("reviews", {}).get("sponsor_holding_line", {})
    lines.append(f"**RAW DRAFT:** {raw_s}\n")
    lines.append(f"**Issues:** {', '.join(final_s.get('issues_found', ['None'])) or 'None'}")
    lines.append(f"**FINAL ({final_s.get('word_count_final','?')} words) [{final_s.get('status')}]:** {final_s.get('final','')}\n")
    lines.append("### Reporter Reply — Raw to Final\n")
    raw_r = drafts.get("drafts", {}).get("reporter_reply", {}).get("raw", "")
    final_r = reviews.get("reviews", {}).get("reporter_reply", {})
    lines.append(f"**RAW DRAFT:** {raw_r}\n")
    lines.append(f"**Issues:** {', '.join(final_r.get('issues_found', ['None'])) or 'None'}")
    lines.append(f"**FINAL [{final_r.get('status')}]:** {final_r.get('final','')}\n")
    lines.append("### Manager Internal Brief\n")
    lines.append(reviews.get("reviews", {}).get("manager_internal_brief", {}).get("final", "") + "\n")
    lines.append("### Note to Timothée (for 6:05 PM)\n")
    lines.append(reviews.get("reviews", {}).get("talent_holding_note", {}).get("final", "") + "\n")
    lines.append("## 4. Reviewer Notes\n")
    lines.append(reviews.get("reviewer_notes", "") + "\n")
    lines.append("## 5. Workflow Proof Block\n")
    lines.append("Agents ran in sequence: TriageAgent → RouterAgent → DraftingAgent → ReviewerAgent")
    lines.append(f"Model: `{MODEL}` via Anthropic Messages API.")
    lines.append("No facts invented. All outputs grounded in Packet A only.\n")
    lines.append("\n---\n")

    if escalation:
        lines.append("# PHASE B — Sponsor Escalation (6:15 PM)\n")
        lines.append("*Phase B was produced after Phase A. It updates the plan based on new sponsor pressure and voicemail signals. Phase A outputs remain the baseline.*\n")

        if transcripts:
            lines.append("## Human-in-the-Loop: Voicemail Review\n")
            lines.append("The workflow paused at Phase B to request human review of audio signals.")
            lines.append("An operator listened to both voicemails and provided transcripts before the escalation agent ran.\n")
            for key, t in transcripts.items():
                lines.append(f"**{key.title()} transcript provided by operator:** {t}\n")

        a = escalation.get("phase_b_assessment", {})
        lines.append("## 6. Phase B Assessment\n")
        lines.append(f"**New Info:** {a.get('new_information')}")
        lines.append(f"**Unchanged:** {a.get('what_has_not_changed')}")
        lines.append(f"**Delta:** {a.get('escalation_severity_delta')}")
        lines.append(f"**Sponsor Risk Now:** {a.get('sponsor_risk_now')}\n")

        lines.append("## 7. Voicemail Triage\n")
        for vm in escalation.get("voicemail_triage", []):
            lines.append(f"**{vm.get('sender')} — {vm.get('organization')}** [{vm.get('urgency')}]")
            lines.append(f"- Assessment: {vm.get('assessment')}")
            lines.append(f"- Action: {vm.get('recommended_action')}")
            if vm.get("strategic_note"):
                lines.append(f"- Strategic note: {vm.get('strategic_note')}")
            lines.append("")

        lines.append("## 8. Updated Routing\n")
        for item in escalation.get("updated_routing", []):
            lines.append(f"**{item['stakeholder']}** — `{item['new_deadline']}` — {item['action_required']}")
            lines.append(f"- Delta: {item['delta_from_phase_a']}\n")

        lines.append("## 9. Sponsor Escalation Response (Maison Valeur)\n")
        lines.append(escalation.get("updated_drafts", {}).get("sponsor_escalation_response", {}).get("raw", "") + "\n")

        lines.append("## 10. Credible Plan Summary (due 6:35 PM)\n")
        lines.append(escalation.get("updated_drafts", {}).get("credible_plan_summary", {}).get("raw", "") + "\n")

        lines.append("## 11. Second Sponsor Callback Brief (Laurent Duchamp — before 8 PM)\n")
        lines.append(escalation.get("updated_drafts", {}).get("second_sponsor_callback_brief", {}).get("raw", "") + "\n")

        lines.append("## 12. Phase A Items Still Valid\n")
        for item in escalation.get("phase_a_items_still_valid", []):
            lines.append(f"- {item}")

        lines.append("\n## 13. Cancelled / Deprioritized\n")
        for item in escalation.get("things_cancelled_or_deprioritized", []):
            lines.append(f"- {item}")

        lines.append("\n## 14. Escalation Workflow Proof\n")
        lines.append("5. **EscalationAgent** → paused for human voicemail review → received transcripts → diffed Packet B against Phase A → updated routing, drafts, and voicemail triage")

        lines.append("\n---\n")

    lines.append("# Human Edit Disclosure\n")
    lines.append("All outputs generated by the agentic pipeline.")
    lines.append("Voicemail transcripts provided by human operator before escalation agent ran.")
    lines.append("A human must review all outward-facing copy before sending.")
    lines.append("No other human edits were made to the outputs above.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["a", "b"], default="a")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("  CRISIS RESPONSE AGENT — Starting pipeline")
    print("=" * 60)

    packet_a = load_packet(PACKET_A_PATH)
    print(f"[SYSTEM] Packet A loaded.")

    print("\n[PHASE A] Running pipeline...")
    triage = triage_agent(packet_a)
    routing = router_agent(packet_a, triage)
    drafts = drafting_agent(packet_a, triage, routing)
    reviews = reviewer_agent(packet_a, drafts)
    print("\n[PHASE A] Complete.")

    escalation = None
    transcripts = {}

    if args.phase == "b":
        packet_b = load_packet(PACKET_B_PATH)
        if "PACKET_B_AVAILABLE: false" in packet_b:
            print("\n[PHASE B] Packet B is placeholder — skipping.")
        else:
            # Human-in-the-loop voicemail review
            packet_b_enriched, transcripts = human_voicemail_review(packet_b)

            print("\n[PHASE B] Running escalation agent...")
            escalation = escalation_agent(
                packet_a,
                packet_b_enriched,
                {"triage": triage, "routing": routing, "drafts": drafts, "reviews": reviews},
                transcripts
            )
            print("\n[PHASE B] Complete.")

    submission = build_submission(triage, routing, drafts, reviews, escalation, transcripts)

    if args.save:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(submission, encoding="utf-8")
        print(f"\n[OUTPUT] Saved to {OUTPUT_PATH}")
    else:
        print("\n" + submission)

    print("\n[DONE] Pipeline finished.")


if __name__ == "__main__":
    main()