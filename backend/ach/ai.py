import json
import logging
import requests
from ai_assistant.models import UserAISettings, OrgAISettings

# Lazy imports for AI providers
try:
    import openai
except ImportError:
    openai = None
try:
    import google.generativeai as genai
except ImportError:
    genai = None
try:
    import anthropic
except ImportError:
    anthropic = None

logger = logging.getLogger(__name__)


def _get_effective_settings(user_settings):
    """Return OrgAISettings if the user has opted in and the org has any AI provider configured."""
    if getattr(user_settings, 'use_org_ai', False):
        org = getattr(user_settings.user, 'organization', None)
        if org:
            try:
                org_settings = OrgAISettings.objects.select_related('shared_profile').get(organization=org)
                effective = org_settings.get_effective_settings()
                if getattr(effective, 'has_any_provider', False):
                    return effective
            except OrgAISettings.DoesNotExist:
                pass
    return user_settings

class ACHGenerator:
    """
    AI generation logic for ACH.
    Interfaces with LLMs to generate hypotheses and evidence based on a scenario description.
    """

    # System prompt for hypothesis/evidence generation.
    _GENERATE_SYSTEM = (
        "You are a Principal Detection Engineer using the Analysis of Competing Hypotheses (ACH) method. "
        "You MUST always interpret the user's scenario in a cybersecurity detection engineering context, "
        "even if the user input is vague, generic, or written like an incident summary. "
        "Generate only detection hypotheses and detection evidence that help design, validate, or improve security detections. "
        "Detection hypotheses must describe plausible adversary behaviors, ATT&CK-aligned techniques, telemetry patterns, "
        "logging assumptions, analytic coverage gaps, or detection opportunities. "
        "Detection evidence must describe observable telemetry, logs, fields, queries, alerts, data sources, enrichment signals, "
        "or validation artifacts that a detection engineer can use to confirm, reject, or tune those hypotheses. "
        "Select only the strongest, most discriminating items for the described scenario. "
        "Return at most 5 hypotheses and at most 6 evidence items. "
        "Do NOT generate generic incident-response, investigative, business, medical, legal, or non-security hypotheses. "
        "Do NOT recommend containment/remediation steps unless they are framed as detection evidence or detection validation context. "
        "Given a scenario description, output ONLY valid JSON with these exact keys: "
        '"hypotheses" (array of detection hypothesis strings) and "evidence" '
        '(array of objects each with "content" (detection evidence string) and "credibility" ("HIGH"|"MEDIUM"|"LOW")). '
        "No markdown, no extra keys, no explanatory text."
    )

    # System prompt for confirmation-bias checking — distinct schema from generation.
    _BIAS_SYSTEM = (
        "You are a critical analyst applying the Analysis of Competing Hypotheses (ACH) method. "
        "Your role is to challenge evidence-hypothesis pairings for confirmation bias. "
        "Output ONLY valid JSON with these exact keys: "
        '"is_biased" (boolean), "warning_message" (short warning string or null if not biased), '
        '"reasoning" (explanation string). '
        "No markdown, no extra keys, no explanatory text."
    )

    # Keep backward-compatible alias so any external code referencing SYSTEM_PROMPT still works.
    SYSTEM_PROMPT = _GENERATE_SYSTEM

    def _get_provider_settings(self, user):
        try:
            settings = UserAISettings.objects.get(user=user)
        except UserAISettings.DoesNotExist:
            # Auto-enable org AI when the organisation already has a provider configured
            use_org_ai = False
            org = getattr(user, 'organization', None)
            if org:
                try:
                    org_settings = OrgAISettings.objects.select_related('shared_profile').get(organization=org)
                    if org_settings.get_effective_settings().has_any_provider:
                        use_org_ai = True
                except OrgAISettings.DoesNotExist:
                    pass
            settings = UserAISettings.objects.create(user=user, use_org_ai=use_org_ai)

        # Use org AI settings when the user has opted in
        effective = _get_effective_settings(settings)

        available = []
        if effective.get_openai_key():
            available.extend(['GPT-5.5', 'GPT-5.4', 'GPT-5.4-MINI'])
        if effective.get_gemini_key():
            available.extend([
                'GEMINI-3.1-PRO-PREVIEW',
                'GEMINI-3.5-FLASH',
                'GEMINI-3-FLASH-PREVIEW',
                'GEMINI-3.1-FLASH-LITE',
                'GEMINI-3.1-FLASH-LITE-PREVIEW',
            ])
        if effective.get_claude_key():
            available.extend(['CLAUDE-OPUS-4.7', 'CLAUDE-SONNET-4.6', 'CLAUDE-HAIKU-4.5-20251001'])
        if effective.get_ollama_url() and effective.get_ollama_model():
            available.append('OLLAMA')
        if (getattr(effective, 'get_azure_openai_key', lambda: '')() and
                getattr(effective, 'get_azure_openai_endpoint', lambda: '')() and
                getattr(effective, 'get_azure_openai_deployment', lambda: '')()):
            available.append('AZURE-OPENAI')

        if not available:
            # No keys configured; fall back with informative error upstream
            return effective, None, []

        provider = effective.preferred_model
        if provider not in available:
            # Fallback priority
            priority_order = [
                'GPT-5.5', 'GPT-5.4', 'GPT-5.4-MINI',
                'GEMINI-3.1-PRO-PREVIEW', 'GEMINI-3.5-FLASH', 'GEMINI-3-FLASH-PREVIEW', 'GEMINI-3.1-FLASH-LITE', 'GEMINI-3.1-FLASH-LITE-PREVIEW',
                'CLAUDE-OPUS-4.7', 'CLAUDE-SONNET-4.6', 'CLAUDE-HAIKU-4.5-20251001',
                'AZURE-OPENAI',
                'OLLAMA',
            ]
            for p in priority_order:
                if p in available:
                    provider = p
                    break
        
        return effective, provider, available

    def generate(self, user, description):
        settings, provider, available = self._get_provider_settings(user)

        if not provider:
            raise Exception("No AI provider configured or available.")

        # XML-delimit user input to reduce prompt injection risk.
        prompt = f"<scenario>\n{description}\n</scenario>"

        try:
            if 'GPT' in provider:
                raw = self._call_openai(settings.get_openai_key(), provider, prompt, self._GENERATE_SYSTEM)
            elif 'GEMINI' in provider:
                raw = self._call_gemini(settings.get_gemini_key(), provider, prompt, self._GENERATE_SYSTEM)
            elif 'CLAUDE' in provider:
                raw = self._call_claude(settings.get_claude_key(), provider, prompt, self._GENERATE_SYSTEM)
            elif provider == 'OLLAMA':
                raw = self._call_ollama(settings.get_ollama_url(), settings.get_ollama_model(), prompt, self._GENERATE_SYSTEM)
            elif provider == 'AZURE-OPENAI':
                raw = self._call_azure_openai(
                    settings.get_azure_openai_endpoint(),
                    settings.get_azure_openai_key(),
                    settings.get_azure_openai_deployment(),
                    prompt,
                    self._GENERATE_SYSTEM,
                )
            else:
                raise Exception(f"Unsupported provider: {provider}")
            return self._normalize_generate_payload(raw)
        except Exception as e:
            logger.error(f"AI Generation failed: {str(e)}")
            raise Exception(f"AI Generation failed: {str(e)}")

    def _normalize_generate_payload(self, data):
        hypotheses_raw = data.get('hypotheses') if isinstance(data, dict) else []
        evidence_raw = data.get('evidence') if isinstance(data, dict) else []

        hypotheses = []
        seen_hypotheses = set()
        for item in (hypotheses_raw or []):
            text = str(item or '').strip()
            if not text:
                continue
            key = text.lower()
            if key in seen_hypotheses:
                continue
            seen_hypotheses.add(key)
            hypotheses.append(text)
            if len(hypotheses) >= 5:
                break

        evidence = []
        seen_evidence = set()
        for item in (evidence_raw or []):
            if not isinstance(item, dict):
                continue
            content = str(item.get('content') or '').strip()
            credibility = str(item.get('credibility') or 'MEDIUM').strip().upper()
            if not content:
                continue
            if credibility not in {'HIGH', 'MEDIUM', 'LOW'}:
                credibility = 'MEDIUM'
            key = content.lower()
            if key in seen_evidence:
                continue
            seen_evidence.add(key)
            evidence.append({'content': content, 'credibility': credibility})
            if len(evidence) >= 6:
                break

        return {'hypotheses': hypotheses, 'evidence': evidence}

    def check_bias(self, user, hypothesis, evidence, score, other_hypotheses):
        settings, provider, available = self._get_provider_settings(user)
        if not provider:
            return None  # Fail silently if no AI

        # XML-delimit user-controlled strings to prevent prompt injection.
        prompt = (
            f"HYPOTHESIS: <hypothesis>{hypothesis}</hypothesis>\n"
            f"EVIDENCE: <evidence>{evidence}</evidence>\n"
            f"USER SCORE: {score}\n"
            f"OTHER HYPOTHESES:\n{json.dumps(other_hypotheses, indent=2)}\n\n"
            "Is this evidence truly diagnostic for the hypothesis alone? "
            "Consider whether the user may be exhibiting Confirmation Bias by ignoring that this evidence "
            "is equally consistent with the other hypotheses listed above."
        )

        try:
            if 'GPT' in provider:
                return self._call_openai(settings.get_openai_key(), provider, prompt, self._BIAS_SYSTEM)
            elif 'GEMINI' in provider:
                return self._call_gemini(settings.get_gemini_key(), provider, prompt, self._BIAS_SYSTEM)
            elif 'CLAUDE' in provider:
                return self._call_claude(settings.get_claude_key(), provider, prompt, self._BIAS_SYSTEM)
            elif provider == 'OLLAMA':
                return self._call_ollama(settings.get_ollama_url(), settings.get_ollama_model(), prompt, self._BIAS_SYSTEM)
            elif provider == 'AZURE-OPENAI':
                return self._call_azure_openai(
                    settings.get_azure_openai_endpoint(),
                    settings.get_azure_openai_key(),
                    settings.get_azure_openai_deployment(),
                    prompt,
                    self._BIAS_SYSTEM,
                )
        except Exception as e:
            logger.error(f"Bias check failed: {e}")
            return None

    def _parse_json_response(self, text):
        # Clean up potential markdown code blocks
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text)

    def _call_openai(self, api_key, model_name, prompt, system_prompt=None):
        if not openai:
            raise Exception("OpenAI library not installed.")

        client = openai.OpenAI(api_key=api_key)

        # Map internal model names to actual OpenAI model IDs
        model_map = {
            'GPT-5.5': 'gpt-5.5',
            'GPT-5.4': 'gpt-5.4',
            'GPT-5.4-MINI': 'gpt-5.4-mini',
        }
        real_model = model_map.get(model_name, 'gpt-5.4-mini')
        sys = system_prompt if system_prompt is not None else self._GENERATE_SYSTEM

        response = client.chat.completions.create(
            model=real_model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        content = response.choices[0].message.content
        return self._parse_json_response(content)

    def _call_gemini(self, api_key, model_name, prompt, system_prompt=None):
        if not genai:
            raise Exception("Google Generative AI library not installed.")

        genai.configure(api_key=api_key)
        sys = system_prompt if system_prompt is not None else self._GENERATE_SYSTEM

        # Map internal model names to current Gemini API identifiers
        model_map = {
            'GEMINI-3.1-PRO-PREVIEW': 'gemini-3.1-pro-preview',
            'GEMINI-3.5-FLASH': 'gemini-3.5-flash',
            'GEMINI-3-FLASH-PREVIEW': 'gemini-3-flash-preview',
            'GEMINI-3.1-FLASH-LITE': 'gemini-3.1-flash-lite',
            'GEMINI-3.1-FLASH-LITE-PREVIEW': 'gemini-3.1-flash-lite-preview',
        }
        desired = model_map.get(model_name, 'gemini-3-flash-preview')

        # Try adaptive selection: pick a model that supports generateContent
        try:
            models = list(genai.list_models())
            # Prefer any flash-capable model; fallback to pro
            preferred = None
            for m in models:
                name = getattr(m, 'name', '') or getattr(m, 'model', '')
                methods = set(getattr(m, 'supported_generation_methods', []) or [])
                if 'generateContent' in methods and 'flash' in name:
                    preferred = name
                    break
            if not preferred:
                for m in models:
                    name = getattr(m, 'name', '') or getattr(m, 'model', '')
                    methods = set(getattr(m, 'supported_generation_methods', []) or [])
                    if 'generateContent' in methods and 'pro' in name:
                        preferred = name
                        break
            real_model = preferred or desired
        except Exception:
            real_model = desired

        try:
            model = genai.GenerativeModel(
                real_model,
                system_instruction=sys,
                generation_config={"response_mime_type": "application/json"},
            )
            response = model.generate_content(prompt)
            return self._parse_json_response(response.text)
        except Exception as e:
            # Fallbacks for older API versions
            for fallback in ['gemini-3.5-flash', 'gemini-3.1-pro-preview', 'gemini-3-flash-preview', 'gemini-3.1-flash-lite', 'gemini-3.1-flash-lite-preview']:
                try:
                    model = genai.GenerativeModel(
                        fallback,
                        system_instruction=sys,
                        generation_config={"response_mime_type": "application/json"},
                    )
                    response = model.generate_content(prompt)
                    return self._parse_json_response(response.text)
                except Exception:
                    continue
            raise e

    def _call_claude(self, api_key, model_name, prompt, system_prompt=None):
        if not anthropic:
            raise Exception("Anthropic library not installed.")

        client = anthropic.Anthropic(api_key=api_key)
        sys = system_prompt if system_prompt is not None else self._GENERATE_SYSTEM

        # Map internal model names
        model_map = {
            'CLAUDE-OPUS-4.7': 'claude-opus-4-7',
            'CLAUDE-SONNET-4.6': 'claude-sonnet-4-6',
            'CLAUDE-HAIKU-4.5-20251001': 'claude-haiku-4-5-20251001',
        }
        real_model = model_map.get(model_name, 'claude-haiku-4-5-20251001')

        message = client.messages.create(
            model=real_model,
            max_tokens=3000,
            system=sys,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_json_response(message.content[0].text)

    def _call_ollama(self, base_url: str, model: str, prompt: str, system_prompt=None):
        sys = system_prompt if system_prompt is not None else self._GENERATE_SYSTEM
        url = base_url.rstrip('/') + '/v1/chat/completions'
        try:
            resp = requests.post(
                url,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": sys},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            raise Exception(f"Cannot connect to Ollama at {base_url}: {e}")
        except requests.exceptions.Timeout:
            raise Exception(f"Ollama request timed out after 120s (model: {model})")
        except requests.exceptions.HTTPError as e:
            raise Exception(f"Ollama API error ({resp.status_code}): {e}")
        data = resp.json()
        text = data['choices'][0]['message']['content']
        return self._parse_json_response(text)

    def _call_azure_openai(self, endpoint: str, api_key: str, deployment: str, prompt: str, system_prompt=None):
        if not openai:
            raise Exception("OpenAI library not installed.")
        sys = system_prompt if system_prompt is not None else self._GENERATE_SYSTEM
        logger.debug("ACHGenerator: calling Azure OpenAI endpoint=%s deployment=%s", endpoint, deployment)
        try:
            client = openai.AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version="2024-02-01",
            )
            response = client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content
            return self._parse_json_response(content)
        except openai.AuthenticationError as e:
            logger.error("Azure OpenAI authentication failed (endpoint=%s): %s", endpoint, e)
            raise Exception(f"Azure OpenAI authentication failed: {e}") from e
        except openai.NotFoundError as e:
            logger.error("Azure OpenAI deployment not found (deployment=%s): %s", deployment, e)
            raise Exception(f"Azure OpenAI deployment '{deployment}' not found: {e}") from e
        except openai.APIConnectionError as e:
            logger.error("Azure OpenAI connection error (endpoint=%s): %s", endpoint, e)
            raise Exception(f"Cannot connect to Azure OpenAI endpoint '{endpoint}': {e}") from e
        except Exception as e:
            logger.error("Azure OpenAI call failed (endpoint=%s, deployment=%s): %s", endpoint, deployment, e)
            raise
