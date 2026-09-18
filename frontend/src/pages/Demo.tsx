import React, { useState, useRef, useEffect } from "react";

type Message = { id: string; text: string; sender: "user" | "bot"; timestamp: Date };
type TraceStep = { id: string; label: string; subLabel?: string; status: "pending" | "success" | "error"; tool?: string; result?: string };

type Channel = "whatsapp" | "gmail";
type FlowStage = "idle" | "request" | "agent_intent" | "tool_call" | "tool_result" | "agent_response" | "response_sent";

export function Demo() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [channel, setChannel] = useState<Channel>("whatsapp");
  
  const [traces, setTraces] = useState<TraceStep[]>([]);
  const [flowStage, setFlowStage] = useState<FlowStage>("idle");
  const [isTyping, setIsTyping] = useState(false);
  const [googleConnected, setGoogleConnected] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(scrollToBottom, [messages, traces, isTyping]);

  const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

  const simulateAgentAction = async (userText: string) => {
    setIsTyping(true);
    setTraces([]);
    setFlowStage("request");
    
    await sleep(600);
    setTraces([{ id: "1", label: "Request received", status: "success" }]);
    setFlowStage("agent_intent");
    
    await sleep(800);
    const textLower = userText.toLowerCase();
    
    let intent = "general";
    if (textLower.includes("meet") || textLower.includes("schedule") || textLower.includes("free")) intent = "schedule";
    if (textLower.includes("email") || textLower.includes("mail")) intent = "email";
    if (textLower.includes("fail")) intent = "fail";

    setTraces(prev => [...prev, { id: "2", label: "Intent detected", subLabel: intent, status: "success" }]);
    
    let reply = "I'm operating in Sandbox mode. I received your message but didn't trigger any specific tools for it.";

    if (intent === "schedule") {
      setFlowStage("tool_call");
      setTraces(prev => [...prev, { id: "3", label: "calendar_check_availability", status: "pending", tool: "Google Calendar" }]);
      await sleep(1000);
      setFlowStage("tool_result");
      setTraces(prev => prev.map(t => t.id === "3" ? { ...t, status: "success", result: "Available: Tomorrow 4:00 PM" } : t));
      
      await sleep(800);
      setFlowStage("tool_call");
      setTraces(prev => [...prev, { id: "4", label: "calendar_create_event", status: "pending", tool: "Google Calendar" }]);
      await sleep(1200);
      setFlowStage("tool_result");
      setTraces(prev => prev.map(t => t.id === "4" ? { ...t, status: "success", result: "Event created successfully" } : t));
      
      reply = "I've checked your calendar and you're free! I have scheduled the meeting for you tomorrow at 4:00 PM.";
    } else if (intent === "email") {
      setFlowStage("tool_call");
      setTraces(prev => [...prev, { id: "3", label: "gmail_search_messages", status: "pending", tool: "Gmail" }]);
      await sleep(1200);
      setFlowStage("tool_result");
      setTraces(prev => prev.map(t => t.id === "3" ? { ...t, status: "success", result: "2 unread emails found" } : t));
      
      reply = "You have 2 unread emails in your inbox right now. Would you like me to read them to you?";
    } else if (intent === "fail") {
      setFlowStage("tool_call");
      setTraces(prev => [...prev, { id: "3", label: "failing_mock_tool", status: "pending", tool: "System" }]);
      await sleep(1000);
      setFlowStage("tool_result");
      setTraces(prev => prev.map(t => t.id === "3" ? { ...t, status: "error", result: "API Rate Limit Exceeded" } : t));
      reply = "I'm sorry, I encountered an error while trying to process that request.";
    }

    setFlowStage("agent_response");
    await sleep(600);
    setTraces(prev => [...prev, { id: "5", label: "Response generated", status: "success" }]);
    
    setFlowStage("response_sent");
    await sleep(400);
    
    setMessages(prev => [...prev, { id: Date.now().toString(), text: reply, sender: "bot", timestamp: new Date() }]);
    setIsTyping(false);
    setTimeout(() => setFlowStage("idle"), 2000);
  };

  const handleSend = (text: string) => {
    if (!text.trim() || isTyping) return;
    setMessages(prev => [...prev, { id: Date.now().toString(), text, sender: "user", timestamp: new Date() }]);
    setInput("");
    simulateAgentAction(text);
  };

  const handleOAuthConnect = () => {
    if (googleConnected) {
      setGoogleConnected(false);
    } else {
      // Live routing to backend OAuth
      window.location.href = "http://localhost:5000/api/integrations/google/auth?tenant_id=demo_tenant&user_id=demo_user";
      // We will pretend it connects if they return, but in a real app this handles OAuth flow.
    }
  };

  const suggestedPrompts = [
    "Am I free tomorrow at 4 PM?",
    "Schedule a meeting with Rahul tomorrow at 4 PM.",
    "Send Rahul an email about the project proposal.",
    "Check my unread emails.",
    "Trigger a tool failure."
  ];

  return (
    <div className="flex h-screen bg-gray-50 text-gray-900 font-sans overflow-hidden">
      
      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/20 z-40 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar: Demo Options & Trace */}
      <div className={`fixed inset-y-0 left-0 transform ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} md:relative md:translate-x-0 transition-transform duration-200 ease-in-out w-80 lg:w-96 border-r border-gray-200 bg-white flex flex-col shadow-lg md:shadow-none z-50`}>
        
        {/* Brand Header */}
        <div className="p-6 border-b border-gray-100 bg-white">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="font-extrabold text-2xl text-gray-900 tracking-tight">WAAS</h1>
              <p className="text-sm font-medium text-gray-500">Agentic AI Workspace</p>
            </div>
            <button className="md:hidden text-gray-400" onClick={() => setSidebarOpen(false)}>
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
          <div className="mt-3 flex items-center">
            <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200 uppercase tracking-wider">
              <svg className="mr-1.5 h-2 w-2 text-amber-500 animate-pulse" fill="currentColor" viewBox="0 0 8 8"><circle cx="4" cy="4" r="3" /></svg>
              Sandbox Mode
            </span>
          </div>
        </div>
        
        <div className="p-6 flex-1 overflow-y-auto bg-gray-50/50">
          
          {/* Integrations Module */}
          <h2 className="text-[11px] font-bold text-gray-500 uppercase tracking-widest mb-3">Integrations</h2>
          <div className="mb-8 border border-gray-200 rounded-xl bg-white shadow-sm overflow-hidden">
            <div className="p-4 border-b border-gray-100">
              <div className="font-semibold text-sm text-gray-800 flex items-center gap-2 mb-3">
                <svg className="w-4 h-4 text-blue-600" viewBox="0 0 24 24" fill="currentColor"><path d="M12.545,10.239v3.821h5.445c-0.712,2.315-2.647,3.972-5.445,3.972c-3.332,0-6.033-2.701-6.033-6.032s2.701-6.032,6.033-6.032c1.498,0,2.866,0.549,3.921,1.453l2.814-2.814C17.503,2.988,15.139,2,12.545,2C7.021,2,2.543,6.477,2.543,12s4.478,10,10.002,10c8.396,0,10.249-7.85,9.426-11.761H12.545z"/></svg>
                Google Workspace
              </div>
              <div className="space-y-2">
                <div className="flex items-center text-xs text-gray-600">
                  <svg className="w-3.5 h-3.5 mr-2 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>
                  Calendar <span className="ml-1 text-gray-400">({googleConnected ? 'Live' : 'Sandbox'})</span>
                </div>
                <div className="flex items-center text-xs text-gray-600">
                  <svg className="w-3.5 h-3.5 mr-2 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>
                  Gmail <span className="ml-1 text-gray-400">({googleConnected ? 'Live' : 'Sandbox'})</span>
                </div>
              </div>
            </div>
            <div className="bg-gray-50 p-3">
              <button 
                onClick={handleOAuthConnect}
                className={`w-full py-2 rounded-lg text-xs font-semibold transition-all ${googleConnected ? 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50' : 'bg-gray-900 text-white hover:bg-gray-800 shadow-sm'}`}
              >
                {googleConnected ? "Connected (Live)" : "Connect Live Google Account"}
              </button>
            </div>
          </div>

          {/* Agentic Flow Vis */}
          <h2 className="text-[11px] font-bold text-gray-500 uppercase tracking-widest mb-3">Agent Flow</h2>
          <div className="mb-8 border border-gray-200 rounded-xl p-4 bg-white shadow-sm flex justify-between items-center text-[10px] font-bold text-gray-400 uppercase tracking-wide">
            <div className={`flex flex-col items-center ${flowStage === 'request' ? 'text-blue-600' : ''}`}>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center mb-1 ${flowStage === 'request' ? 'bg-blue-100' : 'bg-gray-100'}`}>1</div>
              User
            </div>
            <div className={`h-px flex-1 mx-2 ${flowStage === 'agent_intent' ? 'bg-blue-600' : 'bg-gray-200'}`}></div>
            <div className={`flex flex-col items-center ${['agent_intent', 'agent_response'].includes(flowStage) ? 'text-blue-600' : ''}`}>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center mb-1 ${['agent_intent', 'agent_response'].includes(flowStage) ? 'bg-blue-100' : 'bg-gray-100'}`}>2</div>
              Agent
            </div>
            <div className={`h-px flex-1 mx-2 ${['tool_call', 'tool_result'].includes(flowStage) ? 'bg-blue-600' : 'bg-gray-200'}`}></div>
            <div className={`flex flex-col items-center ${['tool_call', 'tool_result'].includes(flowStage) ? 'text-blue-600' : ''}`}>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center mb-1 ${['tool_call', 'tool_result'].includes(flowStage) ? 'bg-blue-100' : 'bg-gray-100'}`}>3</div>
              Tool
            </div>
          </div>

          {/* Agent Activity Trace */}
          <h2 className="text-[11px] font-bold text-gray-500 uppercase tracking-widest mb-3">Agent Activity</h2>
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm min-h-[300px]">
            {traces.length === 0 ? (
              <div className="text-gray-400 text-sm italic text-center mt-10">
                Awaiting interaction...
              </div>
            ) : (
              <div className="space-y-4">
                {traces.map(t => (
                  <div key={t.id} className="relative pl-6 animate-fade-in">
                    {/* Timeline line */}
                    <div className="absolute left-[11px] top-5 bottom-[-20px] w-px bg-gray-200 last:hidden"></div>
                    
                    {/* Status icon */}
                    <div className="absolute left-0 top-1 w-6 h-6 bg-white flex items-center justify-center">
                      {t.status === 'success' ? (
                        <svg className="w-5 h-5 text-emerald-500" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" /></svg>
                      ) : t.status === 'error' ? (
                        <svg className="w-5 h-5 text-red-500" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" /></svg>
                      ) : (
                        <svg className="w-5 h-5 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                      )}
                    </div>
                    
                    <div className="pt-1">
                      <p className="text-sm font-semibold text-gray-800">{t.label}</p>
                      {t.subLabel && <p className="text-xs text-gray-500 mt-0.5">{t.subLabel}</p>}
                      {t.tool && (
                         <div className="mt-1.5 p-2 bg-gray-50 border border-gray-100 rounded-md text-xs">
                           <span className="font-mono text-gray-500">{t.tool}</span>
                           {t.result && (
                             <div className={`mt-1 font-medium ${t.status === 'error' ? 'text-red-600' : 'text-gray-800'}`}>
                               ↳ {t.result}
                             </div>
                           )}
                         </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Chat Interface */}
      <div className="flex-1 flex flex-col bg-white relative">
        
        {/* Chat Header */}
        <div className="h-16 border-b border-gray-200 flex items-center justify-between px-4 sm:px-6 bg-white z-10">
          <div className="flex items-center">
            <button className="md:hidden mr-3 text-gray-400" onClick={() => setSidebarOpen(true)}>
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
            </button>
            <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-gray-900 to-gray-700 flex items-center justify-center mr-3 text-white font-bold shadow-sm text-sm">
              AI
            </div>
            <div>
              <h2 className="font-bold text-gray-900 leading-none">WAAS Agent</h2>
              <p className="text-[11px] text-emerald-600 font-semibold mt-1">Online</p>
            </div>
          </div>
          
          {/* Channel Selector */}
          <div className="flex items-center bg-gray-100 p-1 rounded-lg border border-gray-200">
            <button 
              onClick={() => setChannel("whatsapp")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${channel === 'whatsapp' ? 'bg-white text-emerald-700 shadow-sm border border-gray-200/60' : 'text-gray-500 hover:text-gray-700'}`}
            >
              WhatsApp
            </button>
            <button 
              onClick={() => setChannel("gmail")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${channel === 'gmail' ? 'bg-white text-red-600 shadow-sm border border-gray-200/60' : 'text-gray-500 hover:text-gray-700'}`}
            >
              Gmail
            </button>
          </div>
        </div>

        {/* Chat Messages */}
        <div className="flex-1 overflow-y-auto bg-gray-50">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center p-6 max-w-2xl mx-auto animate-fade-in">
              <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-6 border border-gray-200 shadow-sm">
                <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
              </div>
              <h3 className="text-xl font-bold text-gray-800 mb-2">Welcome to WAAS</h3>
              <p className="text-sm text-gray-500 text-center mb-8 max-w-md leading-relaxed">
                Try asking WAAS to manage your schedule, email, and conversations. Select a prompt below to see the agent in action.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full">
                {suggestedPrompts.map((prompt, i) => (
                  <button 
                    key={i}
                    onClick={() => handleSend(prompt)}
                    className="text-left px-4 py-3 bg-white border border-gray-200 rounded-xl text-sm font-medium text-gray-700 hover:border-blue-300 hover:shadow-sm hover:text-blue-700 transition-all"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="p-4 sm:p-6 space-y-6 max-w-4xl mx-auto">
              {messages.map((m) => (
                <div key={m.id} className={`flex ${m.sender === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[85%] sm:max-w-[70%] px-4 sm:px-5 py-3 shadow-sm ${
                    m.sender === "user" 
                      ? "bg-gray-900 text-white rounded-2xl rounded-tr-sm" 
                      : "bg-white text-gray-800 rounded-2xl rounded-tl-sm border border-gray-200"
                  }`}>
                    <p className="leading-relaxed text-[15px]">{m.text}</p>
                    <span className={`text-[10px] mt-1.5 block font-medium ${m.sender === "user" ? "text-gray-400" : "text-gray-400"}`}>
                      {m.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
              ))}
              
              {isTyping && (
                 <div className="flex justify-start">
                   <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm flex items-center space-x-1.5">
                     <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"></div>
                     <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                     <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                   </div>
                 </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="bg-white border-t border-gray-200 p-4">
          <div className="max-w-4xl mx-auto">
            {/* Sandbox Warning */}
            {!googleConnected && (
              <div className="mb-3 px-3 py-2 bg-amber-50 border border-amber-100 rounded-lg flex items-start sm:items-center">
                <svg className="w-4 h-4 text-amber-500 mr-2 flex-shrink-0 mt-0.5 sm:mt-0" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" /></svg>
                <span className="text-xs text-amber-800 font-medium leading-tight">
                  <strong className="font-bold">SANDBOX MODE:</strong> Simulated Google tools — no real messages or calendar events are created.
                </span>
              </div>
            )}
            
            <form onSubmit={(e) => { e.preventDefault(); handleSend(input); }} className="flex space-x-3 items-end">
              <div className="flex-1 relative">
                <input 
                  className="w-full border border-gray-300 rounded-xl px-4 py-3.5 focus:outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 transition-all text-[15px] bg-gray-50 focus:bg-white shadow-sm"
                  placeholder={`Send a message via ${channel === 'whatsapp' ? 'WhatsApp' : 'Gmail'}...`}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  disabled={isTyping}
                />
              </div>
              <button 
                type="submit" 
                className={`rounded-xl px-5 py-3.5 font-semibold shadow-sm transition-all flex-shrink-0 ${
                  !input.trim() || isTyping 
                    ? 'bg-gray-100 text-gray-400 border border-gray-200 cursor-not-allowed' 
                    : 'bg-gray-900 text-white hover:bg-gray-800 transform hover:-translate-y-0.5'
                }`}
                disabled={!input.trim() || isTyping}
              >
                Send
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
