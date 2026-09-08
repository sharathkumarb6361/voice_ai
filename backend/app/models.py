from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class BusinessBase(BaseModel):
    name: str
    industry: str
    owner_name: str
    phone: str
    email: str
    address: str = ""

class BusinessCreate(BusinessBase):
    pass

class Business(BusinessBase):
    id: str
    created_at: str

class WorkflowField(BaseModel):
    key: str
    label: str
    type: str  # 'text', 'select', 'number', 'datetime'
    options: Optional[List[str]] = []
    required: bool = True
    description: Optional[str] = ""

class WorkflowCondition(BaseModel):
    field: str
    operator: str  # 'equals', 'within_hours', 'exists'
    value: Optional[Any] = None
    action_override: Optional[str] = None
    tool_action: Optional[str] = None
    note: Optional[str] = None

class BusinessHours(BaseModel):
    enabled: bool = True
    days: List[str] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    start_time: str = "09:00"
    end_time: str = "18:00"
    after_hours_greeting: Optional[str] = "We are currently closed. Our operating hours are Mon-Sat 9 AM to 6 PM. We have recorded your request."
    after_hours_action: Optional[str] = "flag_after_hours"

class WorkflowBase(BaseModel):
    business_id: str
    name: str
    industry: str
    trigger_event: str = "Missed Call"
    greeting: str
    fields: List[WorkflowField] = []
    conditions: List[WorkflowCondition] = []
    actions: List[str] = []
    closing_message: str
    language: str = "en-hi"
    business_hours: Optional[BusinessHours] = None
    is_active: int = 1

class WorkflowCreate(WorkflowBase):
    pass

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    greeting: Optional[str] = None
    fields: Optional[List[WorkflowField]] = None
    conditions: Optional[List[WorkflowCondition]] = None
    actions: Optional[List[str]] = None
    closing_message: Optional[str] = None
    language: Optional[str] = None
    business_hours: Optional[BusinessHours] = None
    is_active: Optional[int] = None

class Workflow(WorkflowBase):
    id: str
    created_at: str
    business_name: Optional[str] = None

class ChatMessage(BaseModel):
    role: str  # 'system', 'user', 'assistant', 'tool'
    content: str
    name: Optional[str] = None

class ChatRequest(BaseModel):
    business_id: str
    workflow_id: str
    caller_name: Optional[str] = "Customer"
    caller_phone: Optional[str] = "+91 98765 43210"
    language: Optional[str] = "auto"
    messages: List[ChatMessage]
    record_id: Optional[str] = None

class DeliveryMissedCallRequest(BaseModel):
    caller_name: Optional[str] = "Mobile Caller"
    caller_phone: str
    language: Optional[str] = "auto"

class RecordStatusUpdate(BaseModel):
    status: str

class CalendarEventRequest(BaseModel):
    business_id: Optional[str] = None
    title: str
    start_time: str
    end_time: str
    attendee_name: str
    attendee_phone: str
    description: str = ""

class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    attendee_name: Optional[str] = None
    attendee_phone: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class TTSRequest(BaseModel):
    text: str
    language: Optional[str] = "en"
