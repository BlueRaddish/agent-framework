"""Run one real in-memory Runner and export only to local OTel collectors."""
import asyncio,json,sys
from opentelemetry import _logs,trace
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter,SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
span_exporter=InMemorySpanExporter();span_provider=TracerProvider();span_provider.add_span_processor(SimpleSpanProcessor(span_exporter));trace.set_tracer_provider(span_provider)
log_exporter=InMemoryLogRecordExporter();log_provider=LoggerProvider();log_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter));_logs.set_logger_provider(log_provider)
from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.adk.telemetry import ContentCapturingMode,TelemetryConfig
from google.genai import types
marker='operator-policy-content-marker'
class ScriptedLlm(BaseLlm):
 async def generate_content_async(self,llm_request,stream=False):
  assert any(marker in (part.text or '')for content in llm_request.contents for part in content.parts or [])
  yield LlmResponse(content=types.Content(role='model',parts=[types.Part(text='offline response '+marker)]))
async def main():
 config=TelemetryConfig(capture_message_content=ContentCapturingMode.SPAN_AND_EVENT)
 runner=InMemoryRunner(agent=LlmAgent(name='recipe_check',model=ScriptedLlm(model='offline-scripted')))
 try:
  session=await runner.session_service.create_session(app_name=runner.app_name,user_id='local-user')
  events=[e async for e in runner.run_async(user_id=session.user_id,session_id=session.id,new_message=types.Content(role='user',parts=[types.Part(text='hello '+marker)]),run_config=RunConfig(telemetry=config))]
  assert any(e.is_final_response()for e in events)
 finally:await runner.close()
 span_provider.force_flush();log_provider.force_flush()
 spans=[{'name':s.name,'attributes':dict(s.attributes or {})}for s in span_exporter.get_finished_spans()]
 logs=[{'name':x.log_record.event_name,'body':x.log_record.body,'attributes':dict(x.log_record.attributes or {})}for x in log_exporter.get_finished_logs()]
 assert spans,'No real spans reached the SDK exporter'
 assert any('generate_content'in s['name']or s['name']=='call_llm'for s in spans),spans
 result={'resolved_mode':config.resolved_content_capturing_mode.value,'legacy':config.should_add_content_to_legacy_spans,'log_capture':config.should_add_content_to_logs,'experimental':config.should_add_content_to_experimental_spans,'spans':len(spans),'logs':len(logs),'content_in_spans':marker in json.dumps(spans,default=str),'content_in_logs':marker in json.dumps(logs,default=str),'real_runner_completed':True,'live_model_or_network_calls':0}
 print('OCT25B_ADK_CONSUMER='+json.dumps(result),flush=True)
 assert result['resolved_mode']=='NO_CONTENT'and not any(result[k]for k in ['legacy','log_capture','experimental','content_in_spans','content_in_logs']),result
asyncio.run(main())
