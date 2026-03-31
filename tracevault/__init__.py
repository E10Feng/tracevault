"""TraceVault - tamper-proof audit trails for LangGraph/LangChain agents."""

from .models import TraceEntry, TraceSession
from .storage import TraceStorage
from .chain import sign_entry, verify_entry, verify_chain
from .interceptor import TraceVaultCallbackHandler, trace_session
from .summarizer import Summarizer

__all__ = [
    "TraceEntry",
    "TraceSession",
    "TraceStorage",
    "sign_entry",
    "verify_entry",
    "verify_chain",
    "TraceVaultCallbackHandler",
    "trace_session",
    "Summarizer",
]

__version__ = "0.1.0"
