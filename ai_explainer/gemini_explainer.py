"""Google Gemini-based explanation generator using correct REST API"""
import os
import requests
import json
from .prompt_templates import PromptTemplates


class GeminiExplainer:
    """Generate device health explanations using Google Gemini REST API"""
    
    # Correct model names based on available Gemini 2.x models
    AVAILABLE_MODELS = {
        "flash": "gemini-2.5-flash",
        "pro": "gemini-2.5-pro",
        "flash-lite": "gemini-2.5-flash-lite",
        "flash-2.0": "gemini-2.0-flash"
    }
    
    def __init__(self, api_key=None, model="flash"):
        """
        Initialize Gemini explainer
        
        Args:
            api_key (str): Google AI API key
            model (str): Model to use (flash, pro, flash-lite, flash-2.0)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key not found. Set GEMINI_API_KEY environment variable.")
        
        # Get the full model name
        self.model_name = self.AVAILABLE_MODELS.get(model, self.AVAILABLE_MODELS["flash"])
        
        # Use v1 API
        self.base_url = f"https://generativelanguage.googleapis.com/v1/models/{self.model_name}:generateContent"
        
        print(f"✓ Gemini explainer initialized (Model: {self.model_name})")
    
    def _call_gemini_api(self, prompt, max_tokens=2048):
        """Call Gemini API using REST with correct v1 format"""
        try:
            headers = {"Content-Type": "application/json"}
            
            # Payload format for v1 API with Gemini 2.x
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.3,
                    "topP": 0.95,
                    "topK": 40,
                    "maxOutputTokens": max_tokens,
                    "stopSequences": []
                },
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ]
            }
            
            # Make API call
            url = f"{self.base_url}?key={self.api_key}"
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract text from response
                if 'candidates' in data and len(data['candidates']) > 0:
                    candidate = data['candidates'][0]
                    
                    # Check finish reason
                    finish_reason = candidate.get('finishReason', 'UNKNOWN')
                    
                    if 'content' in candidate and 'parts' in candidate['content']:
                        parts = candidate['content']['parts']
                        if len(parts) > 0 and 'text' in parts[0]:
                            text = parts[0]['text']
                            
                            # Only add warning if actually truncated
                            if finish_reason == 'MAX_TOKENS':
                                text += "\n\n[Warning: Response may be incomplete - reached token limit]"
                            
                            return text.strip()
                
                return "[No response text from Gemini]"
            else:
                error_data = response.json() if response.content else {"error": "Unknown"}
                error_msg = f"API Error {response.status_code}: {json.dumps(error_data, indent=2)}"
                raise Exception(error_msg)
                
        except requests.exceptions.Timeout:
            raise Exception("API request timed out")
        except Exception as e:
            raise e
    
    def explain_device_health(self, device_name, device_data):
        """Generate explanation for a single device's health status"""
        try:
            system_context = PromptTemplates.SYSTEM_PROMPT
            user_prompt = PromptTemplates.build_device_health_prompt(device_name, device_data)
            full_prompt = f"{system_context}\n\n{user_prompt}"
            
            # Increased token limit for complete responses
            explanation = self._call_gemini_api(full_prompt, max_tokens=2048)
            return explanation
            
        except Exception as e:
            print(f"✗ Gemini API error for {device_name}: {e}")
            raise e
    
    def explain_network_health(self, device_summaries):
        """Generate network-wide health analysis"""
        try:
            system_context = PromptTemplates.SYSTEM_PROMPT
            user_prompt = PromptTemplates.build_comparison_prompt(device_summaries)
            full_prompt = f"{system_context}\n\n{user_prompt}"
            
            # Higher token limit for network analysis
            explanation = self._call_gemini_api(full_prompt, max_tokens=2048)
            return explanation
            
        except Exception as e:
            print(f"✗ Gemini API error for network analysis: {e}")
            raise e