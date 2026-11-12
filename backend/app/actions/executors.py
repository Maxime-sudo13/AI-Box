"""Exécution concrète des actions autorisées."""

import smtplib
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Action, AnomalyReview, Company, Document, Invoice, OutboundEmail, Task


class ExecutionError(Exception):
    pass


def _send_email(db: Session, company: Company, action: Action) -> dict[str, Any]:
    settings = get_settings()
    p = action.payload
    msg = EmailMessage()
    sender = settings.mail_from or f"{company.name} <ne-pas-repondre@business-ai-box.local>"
    msg["From"] = sender
    msg["To"] = p["to"]
    msg["Subject"] = p["subject"]
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="business-ai-box.local")
    msg.set_content(p["body"])
    transport = "outbox"
    if settings.smtp_host:
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password or "")
                smtp.send_message(msg)
            transport = "smtp"
        except (OSError, smtplib.SMTPException) as exc:
            raise ExecutionError(f"Le serveur de messagerie a refusé l'envoi : {exc}") from exc
    record = OutboundEmail(
        company_id=company.id,
        action_id=action.id,
        to_address=p["to"],
        subject=p["subject"],
        body=p["body"],
        transport=transport,
        message_id=msg["Message-ID"],
    )
    db.add(record)
    db.flush()
    return {
        "email_id": str(record.id),
        "transport": transport,
        "to": p["to"],
        "message_id": msg["Message-ID"],
        "summary": f"Courriel envoyé à {p['to']}"
        if transport == "smtp"
        else f"Courriel déposé dans la boîte d'envoi (aucun serveur SMTP configuré) pour {p['to']}",
    }


def _create_task(db: Session, company: Company, action: Action) -> dict[str, Any]:
    task = Task(
        company_id=company.id, title=action.payload["title"], details=action.payload.get("details"), action_id=action.id
    )
    db.add(task)
    db.flush()
    return {"task_id": str(task.id), "summary": f"Tâche créée : {task.title}"}


def _undo_task(db: Session, company: Company, action: Action) -> None:
    task = db.get(Task, uuid.UUID(action.result["task_id"]))
    if task:
        db.delete(task)


def _alert_update(db: Session, company: Company, action: Action) -> dict[str, Any]:
    fp = action.payload["fingerprint"]
    review = db.get(AnomalyReview, (company.id, fp))
    previous = review.status if review else None
    if review is None:
        review = AnomalyReview(company_id=company.id, fingerprint=fp)
        db.add(review)
    review.status, review.note = action.payload["status"], action.payload.get("note")
    review.reviewed_at = datetime.now(UTC)
    return {"previous": previous, "summary": f"Alerte passée au statut « {action.payload['status']} »"}


def _undo_alert(db: Session, company: Company, action: Action) -> None:
    review = db.get(AnomalyReview, (company.id, action.payload["fingerprint"]))
    if review and action.result.get("previous") is None:
        db.delete(review)
    elif review:
        review.status = action.result["previous"]


def _categorize(db: Session, company: Company, action: Action) -> dict[str, Any]:
    inv = db.scalar(
        select(Invoice)
        .join(Document)
        .where(Document.id == uuid.UUID(action.payload["document_id"]), Document.company_id == company.id)
    )
    if inv is None:
        raise ExecutionError("Facture introuvable.")
    previous = inv.category
    inv.category = action.payload["category"]
    return {
        "previous": previous,
        "invoice_id": str(inv.id),
        "summary": f"Catégorie changée : {previous} → {inv.category}",
    }


def _undo_categorize(db: Session, company: Company, action: Action) -> None:
    inv = db.get(Invoice, uuid.UUID(action.result["invoice_id"]))
    if inv and inv.company_id == company.id:
        inv.category = action.result["previous"]


def sepa_xml(company: Company, payload: dict[str, Any], msg_id: str) -> str:
    """Ordre de virement au format SEPA pain.001.001.03, accepté par les banques françaises."""
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "")
    amount = Decimal(payload["amount"])
    e = escape
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03">
  <CstmrCdtTrfInitn>
    <GrpHdr><MsgId>{msg_id}</MsgId><CreDtTm>{now}</CreDtTm><NbOfTxs>1</NbOfTxs><CtrlSum>{amount}</CtrlSum>
      <InitgPty><Nm>{e(company.name[:70])}</Nm></InitgPty></GrpHdr>
    <PmtInf><PmtInfId>{msg_id}-1</PmtInfId><PmtMtd>TRF</PmtMtd><NbOfTxs>1</NbOfTxs><CtrlSum>{amount}</CtrlSum>
      <PmtTpInf><SvcLvl><Cd>SEPA</Cd></SvcLvl></PmtTpInf>
      <ReqdExctnDt>{datetime.now(UTC).date().isoformat()}</ReqdExctnDt>
      <Dbtr><Nm>{e(company.name[:70])}</Nm></Dbtr>
      <DbtrAcct><Id><IBAN>{payload["debtor_iban"]}</IBAN></Id></DbtrAcct>
      <DbtrAgt><FinInstnId><Othr><Id>NOTPROVIDED</Id></Othr></FinInstnId></DbtrAgt>
      <CdtTrfTxInf><PmtId><EndToEndId>{msg_id}</EndToEndId></PmtId>
        <Amt><InstdAmt Ccy="EUR">{amount}</InstdAmt></Amt>
        <Cdtr><Nm>{e(payload["creditor_name"])}</Nm></Cdtr>
        <CdtrAcct><Id><IBAN>{payload["creditor_iban"]}</IBAN></Id></CdtrAcct>
        <RmtInf><Ustrd>{e(payload["reference"])}</Ustrd></RmtInf>
      </CdtTrfTxInf>
    </PmtInf>
  </CstmrCdtTrfInitn>
</Document>
"""


def _transfer(db: Session, company: Company, action: Action) -> dict[str, Any]:
    msg_id = f"BAB{action.id.hex[:20].upper()}"
    folder = Path(get_settings().data_dir).resolve() / "virements" / str(company.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{msg_id}.xml"
    path.write_text(sepa_xml(company, action.payload, msg_id), encoding="utf-8")
    return {
        "file": str(path),
        "filename": f"virement-{msg_id}.xml",
        "summary": "Ordre de virement SEPA prêt : téléchargez-le puis déposez-le dans votre banque en ligne. "
        "Aucun paiement n'est émis par le boîtier lui-même.",
    }


EXECUTORS = {
    "task.create": (_create_task, _undo_task),
    "alert.update": (_alert_update, _undo_alert),
    "document.categorize": (_categorize, _undo_categorize),
    "email.payment_reminder": (_send_email, None),
    "email.supplier_request": (_send_email, None),
    "email.cancellation": (_send_email, None),
    "payment.transfer": (_transfer, None),
}
