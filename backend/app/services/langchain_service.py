import os
import json
import re
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_groq import ChatGroq


class SlotCorrection(BaseModel):
    field_key: str = Field(description="Database key of the field being corrected (e.g. cake_flavor, weight_kg, delivery_preference, pickup_location, delivery_location, required_date, custom_message, budget_inr)")
    old_value: Optional[str] = Field(None, description="The previous value being replaced, if known or mentioned")
    new_value: str = Field(description="The new corrected value provided by the caller")
    reason: Optional[str] = Field(None, description="Brief rationale or explanation of the correction")


class TurnCorrectionAnalysis(BaseModel):
    is_correction: bool = Field(description="True if the caller is correcting, updating, or changing any previously stated or assumed information")
    corrections: List[SlotCorrection] = Field(default_factory=list, description="List of corrected fields with old and new values")
    new_extracted_fields: Dict[str, Any] = Field(default_factory=dict, description="Newly supplied fields from this utterance that were not previously present")
    acknowledged_confirmation: Optional[str] = Field(None, description="A natural spoken phrase explicitly acknowledging the correction, e.g. 'Got it, I have updated the flavor to Vanilla instead of Chocolate!'")
    next_field_to_ask: Optional[str] = Field(None, description="The key of the NEXT missing required field that needs to be collected. MUST NOT be a field that has already been answered or just corrected!")
    natural_spoken_reply: str = Field(description="A warm, concise (1-2 sentences) natural spoken response for the phone caller. It acknowledges any corrections warmly, NEVER asks the question for the corrected field again, and naturally asks for the NEXT missing required field (or confirms the request if all fields are done).")


class LangChainService:
    @staticmethod
    def get_llm(model_override: Optional[str] = None) -> Optional[ChatGroq]:
        """Creates a LangChain ChatGroq instance if GROQ_API_KEY is available."""
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return None

        preferred_model = model_override or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        return ChatGroq(
            model=preferred_model,
            api_key=api_key,
            temperature=0.1,
            max_retries=1,
            timeout=3.5
        )

    @staticmethod
    def _convert_messages_to_langchain(messages: List[Dict[str, Any]]) -> List[BaseMessage]:
        """Converts raw dictionary chat messages to LangChain BaseMessage objects."""
        lc_messages: List[BaseMessage] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "assistant":
                lc_messages.append(AIMessage(content=content))
            elif role == "system":
                lc_messages.append(SystemMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))
        return lc_messages

    @staticmethod
    def analyze_and_correct_turn(
        workflow: Dict[str, Any],
        business: Dict[str, Any],
        fields: List[Dict[str, Any]],
        collected_data: Dict[str, Any],
        current_question_field: Optional[str],
        messages: List[Dict[str, Any]],
        language: str = "en",
        caller_name: str = "Customer",
        caller_phone: str = "+91 98765 43210",
        is_after_hours: bool = False
    ) -> TurnCorrectionAnalysis:
        """
        Uses LangChain to analyze multi-turn conversation state, detect caller corrections,
        update database slot values, and generate natural responses that NEVER ask the same
        question again.
        """
        user_messages = [m["content"] for m in messages if m.get("role") == "user"]
        latest_utterance = user_messages[-1] if user_messages else ""

        # Identify missing required fields before this turn
        req_fields = [f for f in fields if f.get("required")]
        missing_before = [f["key"] for f in req_fields if not collected_data.get(f["key"])]

        # Try LangChain ChatGroq Structured Output
        candidate_models = [
            os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            "openai/gpt-oss-20b"
        ]

        for mdl in candidate_models:
            try:
                llm = LangChainService.get_llm(model_override=mdl)
                if not llm:
                    break

                structured_llm = llm.with_structured_output(TurnCorrectionAnalysis)

                clean_collected = {k: v for k, v in collected_data.items() if not k.startswith("_")}
                field_summary = [{"key": f["key"], "label": f.get("label", f["key"]), "required": bool(f.get("required")), "description": f.get("description", "")} for f in fields]

                sys_prompt = (
                    f"You are the intelligent Voice AI telephone representative for '{business.get('name', 'Business')}'.\n"
                    f"Workflow: '{workflow.get('name', 'Customer Assistant')}'.\n"
                    f"Target Language: '{language.upper()}' (en=English, hi=Hindi/Hinglish, kn=Kannada/Kanglish).\n"
                    f"Caller: '{caller_name}', Phone: '{caller_phone}'.\n\n"
                    f"TARGET DATABASE SCHEMA FIELDS:\n{json.dumps(field_summary, indent=2)}\n\n"
                    f"CURRENTLY COLLECTED FIELDS IN DATABASE:\n{json.dumps(clean_collected, indent=2)}\n\n"
                    f"FIELD PREVIOUSLY ASKED TO CALLER: '{current_question_field or 'None'}'\n"
                    f"MISSING REQUIRED FIELDS REMAINING: {json.dumps(missing_before)}\n\n"
                    f"CRITICAL MULTI-TURN CONVERSATION & CORRECTION RULES:\n"
                    f"1. CORRECTION DETECTION & UPDATING:\n"
                    f"   - When the caller provides a correction or changes their mind (e.g. 'Actually make it 2kg', 'Change flavor to Vanilla', 'I meant Red Velvet', 'Store pickup instead of delivery', 'Deliver to Koramangala not Whitefield', 'No message on cake'):\n"
                    f"     * Flag `is_correction = True`.\n"
                    f"     * Record the correction in `corrections` with `field_key`, `old_value`, and `new_value`.\n"
                    f"     * Update that field value in the database state.\n"
                    f"2. NEVER RE-ASK A CORRECTED OR ANSWERED QUESTION:\n"
                    f"   - Once a field has been answered or corrected, DO NOT ask for that field again under any circumstances!\n"
                    f"   - Select the next missing required field that has NOT yet been answered, and ask for that missing field.\n"
                    f"3. NATURAL SPOKEN CONFIRMATION:\n"
                    f"   - Provide a natural spoken confirmation acknowledging the correction (e.g., 'Got it, I\\'ve updated the flavor to Vanilla.').\n"
                    f"   - Seamlessly ask for the next missing field in `natural_spoken_reply` (e.g. 'What custom message would you like written on the cake?').\n"
                    f"   - If all required fields are complete, warmly confirm the order/request and ask if they need anything else.\n"
                    f"4. MID-STREAM CORRECTIONS:\n"
                    f"   - If the assistant was asking for Field B (e.g. 'custom_message'), but the user corrected Field A (e.g. 'Actually change flavor to Vanilla'), accept the correction for Field A, update Field A, and then gently re-ask for Field B without re-asking Field A.\n"
                    f"5. VOICE CONVERSATIONAL STYLE:\n"
                    f"   - Keep `natural_spoken_reply` concise (1-2 natural spoken sentences).\n"
                    f"   - NO markdown, NO asterisks, NO bullet points. Sound like a helpful, polite human on the phone.\n"
                    f"   - Return output in target language code '{language.upper()}'."
                )

                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content=sys_prompt),
                    MessagesPlaceholder(variable_name="chat_history"),
                    ("human", "{latest_utterance}")
                ])

                chain = prompt | structured_llm

                # Prepare history excluding the very last user message (which goes to human slot)
                history_msgs = LangChainService._convert_messages_to_langchain(messages[:-1])

                result: TurnCorrectionAnalysis = chain.invoke({
                    "chat_history": history_msgs,
                    "latest_utterance": latest_utterance
                })

                if result and (result.is_correction or result.corrections or result.natural_spoken_reply):
                    for c in result.corrections:
                        if c.field_key == "delivery_preference":
                            if c.new_value.lower() == "store pickup":
                                c.new_value = "Store Pickup"
                            elif c.new_value.lower() == "home delivery":
                                c.new_value = "Home Delivery"
                    if result.is_correction and result.corrections:
                        reply_lower = (result.natural_spoken_reply or "").lower()
                        first_corr = result.corrections[0]
                        if first_corr.new_value and first_corr.new_value.lower() not in reply_lower and "update" not in reply_lower and "change" not in reply_lower:
                            result.natural_spoken_reply = f"Got it, I have updated the {first_corr.field_key.replace('_', ' ')} to {first_corr.new_value}. {result.natural_spoken_reply}".strip()
                    return result
            except Exception as e:
                print(f"[LangChainService Notice] Model {mdl} execution note: {e}")
                continue

        # Deterministic LangChain Fallback Engine
        return LangChainService._deterministic_fallback_analysis(
            workflow=workflow,
            business=business,
            fields=fields,
            collected_data=collected_data,
            current_question_field=current_question_field,
            latest_utterance=latest_utterance,
            language=language
        )

    @staticmethod
    def _deterministic_fallback_analysis(
        workflow: Dict[str, Any],
        business: Dict[str, Any],
        fields: List[Dict[str, Any]],
        collected_data: Dict[str, Any],
        current_question_field: Optional[str],
        latest_utterance: str,
        language: str = "en"
    ) -> TurnCorrectionAnalysis:
        """
        High-reliability rule-based fallback that analyzes corrections when external LLM is offline.
        Ensures identical state update and non-repeating question behavior.
        """
        u_lower = (latest_utterance or "").lower().strip()
        corrections: List[SlotCorrection] = []
        new_extracted: Dict[str, Any] = {}

        change_cue = bool(re.search(r'\b(actually|change|correct|update|switch|different|instead|modify|reschedule|meant|mean|wrong|another|replace|mistake|make it|not|nah|nahi|badalu|beda)\b', u_lower))

        # 1. Cake Flavor
        flavor_matches = {
            "vanilla": "Vanilla", "vanilla mango": "Vanilla Mango", "mango": "Vanilla Mango",
            "red velvet": "Red Velvet", "velvet": "Red Velvet",
            "belgian dark chocolate": "Belgian Dark Chocolate", "chocolate": "Belgian Dark Chocolate",
            "black forest": "Black Forest", "butterscotch": "Butterscotch", "strawberry": "Strawberry",
            "pineapple": "Pineapple", "blueberry": "Blueberry"
        }
        detected_flavor = None
        for k, name in flavor_matches.items():
            if k in u_lower:
                detected_flavor = name
                break

        if detected_flavor:
            old_flv = collected_data.get("cake_flavor")
            if old_flv and old_flv.lower() != detected_flavor.lower():
                corrections.append(SlotCorrection(
                    field_key="cake_flavor",
                    old_value=old_flv,
                    new_value=detected_flavor,
                    reason="User corrected cake flavor"
                ))
            elif not old_flv:
                new_extracted["cake_flavor"] = detected_flavor

        # 2. Weight (kg)
        w_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:kg|kilo|kilogram|kgs)', u_lower)
        if not w_match and any(w in u_lower for w in ["1kg", "2kg", "3kg", "4kg", "5kg", "0.5kg"]):
            w_match = re.search(r'(\d+(?:\.\d+)?)kg', u_lower)
        if not w_match:
            hi_num_map = {"ek": "1", "do": "2", "teen": "3", "char": "4", "paanch": "5", "aadha": "0.5", "dedh": "1.5", "dhai": "2.5"}
            kn_num_map = {"ondu": "1", "eradu": "2", "mooru": "3", "naalku": "4", "aidu": "5", "ardha": "0.5"}
            num_map = {**hi_num_map, **kn_num_map}
            # Check for negation pattern like "ek kilo nahi, do kilo kardo" or "1kg not, 2kg"
            neg_pat = re.search(r'(?:ek|do|teen|char|\d+)\s*(?:kilo|kg)?\s*(?:nahi|not|beda)[, ]+([a-z0-9.]+)\s*(?:kilo|kg|kardo|kodi)?', u_lower)
            if neg_pat and neg_pat.group(1).strip() in num_map:
                new_w = num_map[neg_pat.group(1).strip()]
                old_w = str(collected_data.get("weight_kg")) if collected_data.get("weight_kg") else "1"
                corrections.append(SlotCorrection(
                    field_key="weight_kg",
                    old_value=old_w,
                    new_value=new_w,
                    reason="User corrected weight via negation"
                ))
                w_match = True
            else:
                for w_word, val in num_map.items():
                    if re.search(r'\b' + w_word + r'\b', u_lower) and ("kilo" in u_lower or "kg" in u_lower or "kardo" in u_lower or "kodi" in u_lower or "weight" in u_lower or change_cue):
                        new_w = val
                        old_w = str(collected_data.get("weight_kg")) if collected_data.get("weight_kg") else None
                        if old_w and old_w != new_w:
                            corrections.append(SlotCorrection(
                                field_key="weight_kg",
                                old_value=old_w,
                                new_value=new_w,
                                reason="User corrected weight"
                            ))
                        elif not old_w:
                            new_extracted["weight_kg"] = new_w
                        w_match = True
                        break

        if w_match and not isinstance(w_match, bool):
            new_w = w_match.group(1)
            old_w = str(collected_data.get("weight_kg")) if collected_data.get("weight_kg") else None
            if old_w and old_w != new_w:
                corrections.append(SlotCorrection(
                    field_key="weight_kg",
                    old_value=old_w,
                    new_value=new_w,
                    reason="User corrected weight"
                ))
            elif not old_w:
                new_extracted["weight_kg"] = new_w

        # 3. Delivery Preference
        has_delivery = any(w in u_lower for w in ["home delivery", "deliver it", "send to home", "delivery please", "delivery"])
        has_pickup = any(w in u_lower for w in ["store pickup", "pickup", "pick up", "takeaway", "collect from store"])

        if "instead of" in u_lower or change_cue:
            if has_pickup and ("delivery" in u_lower or collected_data.get("delivery_preference") == "Home Delivery"):
                corrections.append(SlotCorrection(
                    field_key="delivery_preference",
                    old_value=collected_data.get("delivery_preference", "Home Delivery"),
                    new_value="Store Pickup",
                    reason="User corrected to Store Pickup"
                ))
            elif has_delivery and ("pickup" in u_lower or collected_data.get("delivery_preference") == "Store Pickup"):
                corrections.append(SlotCorrection(
                    field_key="delivery_preference",
                    old_value=collected_data.get("delivery_preference", "Store Pickup"),
                    new_value="Home Delivery",
                    reason="User corrected to Home Delivery"
                ))
        elif has_pickup:
            new_extracted["delivery_preference"] = "Store Pickup"
        elif has_delivery:
            new_extracted["delivery_preference"] = "Home Delivery"

        # 4. Logistics locations & details
        pick_change = re.search(r'(?:pickup|pick up)\s+(?:from|at|is)\s+([a-zA-Z\s]+?)(?:\s+instead|\s*$)', u_lower) or \
                      re.search(r'change\s+(?:the\s+)?pickup(?:\s+location)?\s+to\s+([a-zA-Z\s]+)', u_lower)
        if pick_change and ("pickup_location" in [f["key"] for f in fields] or "logistics" in str(workflow.get("industry", "")).lower()):
            new_pick = pick_change.group(1).strip().title()
            old_pick = collected_data.get("pickup_location")
            if old_pick and old_pick.lower() != new_pick.lower():
                corrections.append(SlotCorrection(
                    field_key="pickup_location",
                    old_value=old_pick,
                    new_value=new_pick,
                    reason="User updated pickup location"
                ))
            elif not old_pick:
                new_extracted["pickup_location"] = new_pick

        loc_change = re.search(r'(?:deliver(?:y)?|send|deliver it)\s+(?:to|at)\s+([a-zA-Z\s]+?)(?:\s+instead|\s*$)', u_lower) or \
                     re.search(r'change\s+(?:the\s+)?delivery(?:\s+location)?\s+to\s+([a-zA-Z\s]+)', u_lower)
        if loc_change and ("delivery_location" in [f["key"] for f in fields] or "logistics" in str(workflow.get("industry", "")).lower()):
            new_loc = loc_change.group(1).strip().title()
            old_loc = collected_data.get("delivery_location")
            if old_loc and old_loc.lower() != new_loc.lower():
                corrections.append(SlotCorrection(
                    field_key="delivery_location",
                    old_value=old_loc,
                    new_value=new_loc,
                    reason="User updated delivery destination"
                ))
            elif not old_loc:
                new_extracted["delivery_location"] = new_loc

        # 5. Logistics package types
        for p_norm, p_terms in [("documents", ("documents", "document", "papers", "files")), ("electronics", ("electronics", "electronic", "laptop")), ("parcel", ("parcel", "box")), ("small package", ("small package", "small parcel"))]:
            if any(term in u_lower for term in p_terms) and ("package_type" in [f["key"] for f in fields] or "logistics" in str(workflow.get("industry", "")).lower()):
                old_pkg = collected_data.get("package_type")
                if old_pkg and old_pkg.lower() != p_norm:
                    corrections.append(SlotCorrection(
                        field_key="package_type",
                        old_value=old_pkg,
                        new_value=p_norm,
                        reason="User updated package type"
                    ))
                elif not old_pkg:
                    new_extracted["package_type"] = p_norm
                break

        is_correction = len(corrections) > 0 or change_cue

        # Build merged state to determine next missing field
        simulated_state = dict(collected_data)
        for c in corrections:
            simulated_state[c.field_key] = c.new_value
        for k, v in new_extracted.items():
            simulated_state[k] = v

        req_fields = [f for f in fields if f.get("required")]
        missing_after = [f["key"] for f in req_fields if not simulated_state.get(f["key"])]

        next_field = missing_after[0] if missing_after else None

        # Generate natural spoken confirmation acknowledging correction
        ack_phrases = []
        for c in corrections:
            clean_name = c.field_key.replace("_", " ")
            ack_phrases.append(f"{clean_name} to {c.new_value}")

        ack_text = ""
        if ack_phrases:
            if language == "kn":
                ack_text = f"Kanditha, naanu {', '.join(ack_phrases)} update madiddene."
            elif language == "hi":
                ack_text = f"Zaroor, maine {', '.join(ack_phrases)} update kar diya hai."
            else:
                ack_text = f"Got it, I have updated the {', '.join(ack_phrases)}."

        # Generate question for next field (ensuring corrected field is NOT asked!)
        next_q = ""
        if next_field == "weight_kg":
            next_q = "How many kilograms would you like the cake to be?"
        elif next_field == "cake_flavor":
            next_q = "What flavor cake would you like?"
        elif next_field == "required_date":
            next_q = "What date and time do you need the cake ready?"
        elif next_field == "custom_message":
            next_q = "What message would you like written on the cake?"
        elif next_field == "delivery_preference":
            next_q = "Would you prefer Home Delivery to your doorstep, or Store Pickup from our bakery?"
        elif next_field == "budget_inr":
            next_q = "What is your approximate budget for the cake in rupees?"
        elif next_field == "delivery_location":
            next_q = "Where should we deliver the package (destination address)?"
        elif next_field == "pickup_location":
            next_q = "Where should we pick up the package from?"
        elif not next_field:
            if language == "kn":
                next_q = "Nimma order confirm agide. Berenu badalavane madabeka?"
            elif language == "hi":
                next_q = "Aapka order confirm ho gaya hai. Kya aap kuch aur badalna chahenge?"
            else:
                next_q = "Your order details are updated and confirmed. Would you like to make any other changes?"

        spoken = f"{ack_text} {next_q}".strip() if ack_text else next_q

        return TurnCorrectionAnalysis(
            is_correction=is_correction,
            corrections=corrections,
            new_extracted_fields=new_extracted,
            acknowledged_confirmation=ack_text or None,
            next_field_to_ask=next_field,
            natural_spoken_reply=spoken
        )
