from abc import ABC, abstractmethod
from email.message import EmailMessage
from email.utils import parseaddr
import smtplib
import uuid
from app.core.config import get_settings

class EmailProvider(ABC):
    @abstractmethod
    def send(self,*,to:str,subject:str,content:str,idempotency_key:str)->dict: ...
class MockEmailProvider(EmailProvider):
    def send(self,**kwargs): return {"provider_message_id":f"mock-{uuid.uuid4()}","state":"SENT"}
class SMTPEmailProvider(EmailProvider):
    def __init__(self):
        self.settings=get_settings()
        if not self.settings.smtp_host or not self.settings.smtp_username or not self.settings.smtp_password:
            raise RuntimeError("SMTP_HOST, SMTP_USERNAME and SMTP_PASSWORD are required")
    def send(self,*,to:str,subject:str,content:str,idempotency_key:str)->dict:
        message=EmailMessage(); message["From"]=self.settings.email_from; message["To"]=to; message["Subject"]=subject
        message["Message-ID"]=f"<{uuid.uuid5(uuid.NAMESPACE_URL,idempotency_key)}@{parseaddr(self.settings.email_from)[1].split('@')[-1]}>"; message.set_content(content)
        with smtplib.SMTP(self.settings.smtp_host,self.settings.smtp_port,timeout=20) as client:
            if self.settings.smtp_starttls: client.starttls()
            client.login(self.settings.smtp_username,self.settings.smtp_password); client.send_message(message)
        return {"provider_message_id":message["Message-ID"],"state":"SENT"}
def provider():
    settings=get_settings()
    if settings.email_provider=="mock": return MockEmailProvider()
    if settings.email_provider=="smtp": return SMTPEmailProvider()
    raise RuntimeError("Real email provider adapter is not configured")
