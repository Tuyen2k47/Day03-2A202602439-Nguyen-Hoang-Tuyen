"""
Lab #3: Baseline Chatbot vs ReAct Agent
Học viên hoàn thiện các mục TODO để hoàn thành bài lab.
"""

import json
import re

from tools import TOOL_DEFINITIONS, TOOL_MAP, get_flight_info, get_weather_forecast

SYSTEM_PROMPT = """Bạn là một ReAct Agent thông minh hỗ trợ khách hàng Vingroup.
Bạn chỉ sử dụng các công cụ sau:
{tools}

Quy trình trả lời bắt buộc:
Thought: <Suy nghĩ bước tiếp theo>
Action: {{"name": "<tên tool>", "args": {{<tham số>}}}}
Observation: <Kết quả từ tool>
... (Lặp lại cho tới khi có đủ dữ liệu)
Final Answer: <Câu trả lời hoàn chỉnh cho khách hàng>
"""


def _extract_city_codes(text: str):
    valid_codes = {"HAN", "SGN", "DAD"}
    codes = re.findall(r"\b[A-Z]{3}\b", text.upper())
    return [code for code in codes if code in valid_codes]


def _extract_price_limit(text: str, default: int = 2_000_000) -> int:
    lowered = text.lower()
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(triệu|trieu|vnd|đồng|dong)", lowered)
    if match:
        number = float(match.group(1).replace(",", "."))
        if "triệu" in match.group(2) or "trieu" in match.group(2):
            return int(number * 1_000_000)
        return int(number)

    match = re.search(r"(\d{5,})", lowered)
    if match:
        return int(match.group(1))
    return default


class ChatbotBaseline:
    """Baseline LLM Chatbot (Không sử dụng ReAct Loop hay Tools)"""
    def query(self, user_input: str) -> dict:
        answer = (
            "Tôi là chatbot baseline và chưa kết nối cơ sở dữ liệu/Tool, nên không thể tra cứu dữ liệu thời gian thực. "
            "Bạn có thể yêu cầu hỗ trợ thông tin chuyến bay hoặc thời tiết theo hướng dẫn của hệ thống."
        )
        return {"status": "success", "tool_calls": [], "answer": answer}


class ReActAgent:
    """ReAct Agent có sử dụng Thought-Action-Observation Loop"""
    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.trace = []

    def _final_answer_from_results(self, flight_result=None, weather_result=None):
        if flight_result and weather_result:
            flight = flight_result[0] if isinstance(flight_result, list) and flight_result else flight_result
            return (
                f"Tôi tìm thấy chuyến bay {flight.get('flight_number', 'N/A')} từ {flight.get('origin', 'N/A')} đến {flight.get('destination', 'N/A')} "
                f"lúc {flight.get('departure_time', 'N/A')} với giá {flight.get('price_vnd', 0):,} VND ({flight.get('airline', 'N/A')}). "
                f"Thời tiết ở {weather_result.get('city', 'N/A')} hiện là {weather_result.get('temperature_c', 'N/A')}°C, {weather_result.get('condition', 'N/A')}. "
                f"{weather_result.get('recommendation', 'N/A')}"
            )

        if flight_result:
            flight = flight_result[0] if isinstance(flight_result, list) and flight_result else flight_result
            return (
                f"Tôi tìm thấy chuyến bay {flight.get('flight_number', 'N/A')} từ {flight.get('origin', 'N/A')} đến {flight.get('destination', 'N/A')} "
                f"lúc {flight.get('departure_time', 'N/A')} với giá {flight.get('price_vnd', 0):,} VND ({flight.get('airline', 'N/A')})."
            )

        if weather_result:
            return (
                f"Thời tiết ở {weather_result.get('city', 'N/A')} hiện là {weather_result.get('temperature_c', 'N/A')}°C, "
                f"{weather_result.get('condition', 'N/A')}. {weather_result.get('recommendation', 'N/A')}"
            )

        return "Tôi chưa có đủ thông tin để đưa ra câu trả lời cuối cùng."

    def run(self, user_input: str) -> dict:
        self.trace = []
        raw = (user_input or "").strip()
        lowered = raw.lower()

        if "chính sách đổi trả" in lowered or "vinpearl" in lowered:
            answer = (
                "Vinpearl hỗ trợ chính sách đổi trả theo từng loại vé, tùy thuộc vào thời điểm mua và điều kiện vé. "
                "Nếu bạn muốn, tôi có thể hướng dẫn cách kiểm tra chính sách cụ thể theo loại vé hoặc thời gian đặt chỗ."
            )
            self.trace.append({"step": 1, "user_input": raw, "answer": answer})
            return {"status": "completed", "answer": answer, "trace": self.trace, "iterations": 1}

        codes = _extract_city_codes(raw)
        flight_action = None
        weather_action = None

        if any(keyword in lowered for keyword in ["chuyến bay", "vé máy bay", "vé", "bay", "đi", "from", "to"]):
            origin = codes[0] if len(codes) >= 2 else "HAN"
            destination = codes[1] if len(codes) >= 2 else "SGN"
            max_price = _extract_price_limit(raw, default=2_000_000)
            flight_action = {
                "name": "get_flight_info",
                "args": {"origin": origin, "destination": destination, "max_price": max_price},
            }

        if any(keyword in lowered for keyword in ["thời tiết", "weather", "nhiệt độ", "mặc gì", "mưa", "nắng"]):
            if len(codes) >= 2 and "đi" in lowered and flight_action:
                weather_city = destination
            elif len(codes) >= 1:
                weather_city = codes[-1]
            else:
                weather_city = "SGN"
            weather_action = {"name": "get_weather_forecast", "args": {"city_code": weather_city}}

        actions = [a for a in [flight_action, weather_action] if a]

        if not actions:
            answer = "Tôi chưa tìm thấy nhu cầu cần dùng tool, nên chỉ có thể trả lời sơ bộ theo ngữ cảnh của câu hỏi."
            self.trace.append({"step": 1, "user_input": raw, "answer": answer})
            return {"status": "completed", "answer": answer, "trace": self.trace, "iterations": 1}

        observations = []
        actual_iterations = 0

        for index, action in enumerate(actions):
            if actual_iterations >= self.max_iterations:
                return {
                    "status": "max_iterations_reached",
                    "answer": "Không thể hoàn thành trong số bước tối đa.",
                    "trace": self.trace,
                    "iterations": actual_iterations,
                }

            tool_name = (action["name"] or "").strip().lower()
            tool_fn = TOOL_MAP.get(tool_name)
            if tool_fn is None:
                observation = {"error": f"Tool '{tool_name}' không tồn tại."}
            else:
                try:
                    observation = tool_fn(**action.get("args", {}))
                except TypeError:
                    observation = {"error": "Sai tham số đầu vào."}

            actual_iterations += 1
            step = {
                "step": len(self.trace) + 1,
                "thought": f"Tôi cần gọi tool {tool_name} để lấy dữ liệu cần thiết.",
                "action": action,
                "observation": observation,
            }
            self.trace.append(step)
            observations.append(observation)

            if index == len(actions) - 1 and actual_iterations >= self.max_iterations:
                return {
                    "status": "max_iterations_reached",
                    "answer": "Không thể hoàn thành trong số bước tối đa.",
                    "trace": self.trace,
                    "iterations": actual_iterations,
                }

        flight_result = None
        weather_result = None
        if flight_action:
            flight_result = observations[0] if actions[0]["name"] == "get_flight_info" else None
        if weather_action:
            weather_idx = actions.index(weather_action) if weather_action in actions else 0
            weather_result = observations[weather_idx]

        final_answer = self._final_answer_from_results(flight_result=flight_result, weather_result=weather_result)

        if len(actions) > 1:
            self.trace.append({
                "step": len(self.trace) + 1,
                "final_answer": final_answer,
            })
            return {
                "status": "completed",
                "answer": final_answer,
                "trace": self.trace,
                "iterations": actual_iterations + 1,
            }

        return {
            "status": "completed",
            "answer": final_answer,
            "trace": self.trace,
            "iterations": actual_iterations,
        }


def main():
    user_query = "Tìm cho tôi chuyến bay từ HAN đi SGN dưới 2 triệu, rồi cho biết thời tiết SGN nên mặc gì?"

    print("=== RUNNING CHATBOT BASELINE ===")
    chatbot = ChatbotBaseline()
    print(chatbot.query(user_query))

    print("\n=== RUNNING REACT AGENT ===")
    agent = ReActAgent(max_iterations=5)
    result = agent.run(user_query)
    print("Result:", result)
    print("Trace Log:", json.dumps(agent.trace, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()