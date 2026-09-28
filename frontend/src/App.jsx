import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, User, Menu, FileText, X, Paperclip, Mic, MicOff, RotateCcw } from 'lucide-react';

const API_BASE_URL = 'http://localhost:8200';

const indianStates = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
    "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry"
];

const getAgeGroup = (ageStr) => {
    const age = parseInt(ageStr, 10);
    if (isNaN(age)) return '';
    if (age <= 6) return '0–6';
    if (age <= 12) return '7–12';
    if (age <= 18) return '13–18';
    if (age <= 25) return '19–25';
    if (age <= 50) return '26–50';
    if (age <= 60) return '51–60';
    return '60+';
};

function App() {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [status, setStatus] = useState(null);
    const [file, setFile] = useState(null);
    const [isUploading, setIsUploading] = useState(false);
    const [showEligibilityForm, setShowEligibilityForm] = useState(false);
    const [eligibilityData, setEligibilityData] = useState({
        name: '', age: '', ageGroup: '', gender: '', maritalStatus: '', state: '',
        occupation: '', income: '', bplStatus: '', disability: '', locationType: ''
    });
    const [eligibilityStep, setEligibilityStep] = useState(1);

    // Widget State
    const [widgetOpen, setWidgetOpen] = useState(false);
    const [widgetMinimized, setWidgetMinimized] = useState(false);
    const [widgetMaximized, setWidgetMaximized] = useState(false);

    const messagesEndRef = useRef(null);
    const fileInputRef = useRef(null);
    const autoAdvanceTimeoutRef = useRef(null);
    const recognitionRef = useRef(null);
    const [selectedLanguage, setSelectedLanguage] = useState('English');
    const [showLangMenu, setShowLangMenu] = useState(false);
    const [isListening, setIsListening] = useState(false);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, isLoading]);

    useEffect(() => {
        fetchStatus();
        fetchConversations();
    }, []);

    useEffect(() => {
        const SpeechRecognitionLib = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognitionLib) {
            recognitionRef.current = new SpeechRecognitionLib();
            recognitionRef.current.continuous = false;
            recognitionRef.current.interimResults = false;

            recognitionRef.current.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                setInput(prev => (prev ? prev + " " + transcript : transcript));
                setIsListening(false);
            };

            recognitionRef.current.onerror = (e) => {
                console.error("Speech recognition error", e);
                setIsListening(false);
            };

            recognitionRef.current.onend = () => {
                setIsListening(false);
            };
        }
    }, []);

    const toggleListening = () => {
        if (!recognitionRef.current) {
            alert("Speech Recognition is not supported in your browser.");
            return;
        }

        if (isListening) {
            recognitionRef.current.stop();
            setIsListening(false);
        } else {
            const langMap = { 'English': 'en-IN', 'हिंदी': 'hi-IN', 'मराठी': 'mr-IN' };
            recognitionRef.current.lang = langMap[selectedLanguage] || 'en-IN';
            try {
                recognitionRef.current.start();
                setIsListening(true);
            } catch (e) {
                console.error(e);
            }
        }
    };

    const fetchStatus = async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/status`, { credentials: 'include' });
            const data = await res.json();
            setStatus(data);
        } catch (error) {
            console.error('Failed to fetch status:', error);
        }
    };

    const fetchConversations = async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/conversations`, { credentials: 'include' });
            const data = await res.json();
            if (data.conversations && data.conversations.length > 0) {
                setMessages(data.conversations);
            }
        } catch (error) {
            console.error('Failed to fetch conversations:', error);
        }
    };

    const suggestions = [
        { text: "Farmer Schemes", icon: "🌾" },
        { text: "Women Schemes", icon: "👩" },
        { text: "Student Scholarships", icon: "🎓" },
        { text: "Housing Schemes", icon: "🏠" },
        { text: "MSME & Startup", icon: "💼" },
        { text: "Health Schemes", icon: "🏥" },
        { text: "Pension Schemes", icon: "👴" },
        { text: "Skill Development", icon: "🛠️" },
        { text: "Check Your Eligibility", icon: "✅" }
    ];

    const handleSuggestionClick = (text) => {
        if (text === "Check Your Eligibility") {
            setEligibilityData({
                name: '', age: '', ageGroup: '', gender: '', maritalStatus: '', state: '',
                occupation: '', income: '', bplStatus: '', disability: '', locationType: ''
            });
            setEligibilityStep(1);
            setShowEligibilityForm(true);
        } else {
            sendMessage(null, `Tell me about ${text}`);
        }
    };

    const handleEligibilitySubmit = () => {
        const prompt = `Please find eligible schemes for me. Here are my details:
- Name: ${eligibilityData.name}
- Age: ${eligibilityData.age} (Group: ${eligibilityData.ageGroup})
- Gender: ${eligibilityData.gender}
- Marital Status: ${eligibilityData.maritalStatus}
- State: ${eligibilityData.state}
- Occupation: ${eligibilityData.occupation}
- Annual Income: ${eligibilityData.income}
- BPL Status: ${eligibilityData.bplStatus}
- Disability: ${eligibilityData.disability}
- Location Type: ${eligibilityData.locationType}

Please show only real government schemes available in ${eligibilityData.state} and Central Government schemes.`;
        setShowEligibilityForm(false);
        sendMessage(null, prompt);
    };

    const handleOptionSelect = (field, value, targetStep) => {
        setEligibilityData(prev => ({ ...prev, [field]: value }));
        if (autoAdvanceTimeoutRef.current) {
            clearTimeout(autoAdvanceTimeoutRef.current);
        }
        if (targetStep < 10) {
            autoAdvanceTimeoutRef.current = setTimeout(() => {
                setEligibilityStep(prev => (prev === targetStep ? prev + 1 : prev));
            }, 500);
        }
    };

    const sendMessage = async (e, customMessage = null) => {
        e?.preventDefault();
        const userMessage = (customMessage || input).trim();
        if (!userMessage && !file) return;

        setInput('');
        setIsLoading(true);

        if (userMessage) {
            setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
        }

        try {
            const res = await fetch(`${API_BASE_URL}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: userMessage, language: selectedLanguage }),
                credentials: 'include'
            });

            const data = await res.json();

            if (res.ok) {
                setMessages(prev => [...prev, { role: 'assistant', content: data.response }]);
            } else {
                setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${data.response || data.error}` }]);
            }
        } catch (error) {
            setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Connection to server failed. Please ensure the backend is running.' }]);
        } finally {
            setIsLoading(false);
        }
    };

    const resetChat = async () => {
        const confirmMsg = selectedLanguage === 'मराठी' ? 'तुम्हाला खात्री आहे की तुम्ही चॅट रीसेट करू इच्छिता?' : selectedLanguage === 'हिंदी' ? 'क्या आप वाकई चैट रीसेट करना चाहते हैं?' : 'Are you sure you want to reset the chat?';
        if (!window.confirm(confirmMsg)) return;

        try {
            const res = await fetch(`${API_BASE_URL}/newchat`, {
                method: 'POST',
                credentials: 'include'
            });
            if (res.ok) {
                setMessages([]);
                setInput('');
                setFile(null);
                if (fileInputRef.current) fileInputRef.current.value = "";
                // Refresh status and conversations
                fetchStatus();
            } else {
                const errorData = await res.json();
                console.error('Reset failed:', errorData);
            }
        } catch (error) {
            console.error('Failed to reset chat:', error);
        }
    };

    const showSuggestions = messages.length === 0 || (messages.length === 1 && messages[0].isWelcome);

    // Widget panel CSS class
    const widgetPanelClass = `widget-panel${widgetMinimized ? ' minimized' : ''}${widgetMaximized ? ' maximized' : ''}`;

    return (
        <>
            {/* Floating Bubble */}
            {!widgetOpen && (
                <button
                    className="widget-bubble"
                    onClick={() => { setWidgetOpen(true); setWidgetMinimized(false); }}
                    title="Open Sarkar Mitra"
                >
                    🏛️
                </button>
            )}

            {/* Widget Panel */}
            {widgetOpen && (
                <div className={widgetPanelClass}>
                    {/* Widget Header */}
                    <div className="widget-header">
                        <div className="widget-header-left">
                            <div className="widget-header-avatar" style={{ fontSize: '0.9rem', fontWeight: 'bold' }}>my</div>
                            <div className="widget-header-title">
                                <span className="wt-name">myScheme <span style={{ background: '#e2e8f0', color: '#475569', padding: '2px 6px', borderRadius: '4px', fontSize: '0.7rem', verticalAlign: 'middle', marginLeft: '4px', fontWeight: 'bold' }}>Chat</span></span>
                                <span className="wt-status">● Online</span>
                            </div>
                        </div>
                        <div className="widget-header-controls">
                            {/* Minimize */}
                            <button
                                className="widget-ctrl-btn"
                                onClick={() => setWidgetMinimized(v => !v)}
                                title={widgetMinimized ? 'Restore' : 'Minimize'}
                            >
                                {widgetMinimized ? '▲' : '—'}
                            </button>
                            {/* Maximize */}
                            <button
                                className="widget-ctrl-btn"
                                onClick={() => { setWidgetMaximized(v => !v); setWidgetMinimized(false); }}
                                title={widgetMaximized ? 'Restore Size' : 'Maximize'}
                            >
                                {widgetMaximized ? '❐' : '⛶'}
                            </button>
                            {/* Close */}
                            <button
                                className="widget-ctrl-btn close"
                                onClick={() => { setWidgetOpen(false); setWidgetMaximized(false); setWidgetMinimized(false); }}
                                title="Close"
                            >
                                ✕
                            </button>
                        </div>
                    </div>

                    {/* Chat Body (hidden when minimized) */}
                    {!widgetMinimized && (
                        <div className="app-container" style={{ height: 'calc(100% - 56px)', width: '100%', position: 'relative' }}>
                            <AnimatePresence>
                                {showEligibilityForm && (
                                    <div className="modal-overlay" onClick={() => setShowEligibilityForm(false)}>
                                        <motion.div
                                            className="eligibility-modal"
                                            onClick={e => e.stopPropagation()}
                                            initial={{ opacity: 0, scale: 0.95, y: 20 }}
                                            animate={{ opacity: 1, scale: 1, y: 0 }}
                                            exit={{ opacity: 0, scale: 0.95, y: 20 }}
                                        >
                                            <button className="close-modal-btn" onClick={() => setShowEligibilityForm(false)}><X size={20} /></button>
                                            <h2>Check Your Eligibility</h2>
                                            <div className="stepper">Step {eligibilityStep} of 10</div>

                                            <div className="step-content">
                                                {eligibilityStep === 1 && (
                                                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                                                        <label>What is your full name?</label>
                                                        <input
                                                            type="text"
                                                            value={eligibilityData.name}
                                                            onChange={e => setEligibilityData({ ...eligibilityData, name: e.target.value })}
                                                            onKeyDown={e => {
                                                                if (e.key === 'Enter' && eligibilityData.name.trim()) {
                                                                    e.preventDefault();
                                                                    setEligibilityStep(prev => prev + 1);
                                                                }
                                                            }}
                                                            placeholder="Enter your name"
                                                            className="form-input"
                                                            autoFocus
                                                        />
                                                    </motion.div>
                                                )}
                                                {eligibilityStep === 2 && (
                                                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                                                        <label>What is your age?</label>
                                                        <input
                                                            type="number"
                                                            value={eligibilityData.age}
                                                            onChange={e => setEligibilityData({ ...eligibilityData, age: e.target.value, ageGroup: getAgeGroup(e.target.value) })}
                                                            onKeyDown={e => {
                                                                if (e.key === 'Enter' && eligibilityData.age) {
                                                                    e.preventDefault();
                                                                    setEligibilityStep(prev => prev + 1);
                                                                }
                                                            }}
                                                            placeholder="Enter your age"
                                                            className="form-input"
                                                            autoFocus
                                                        />
                                                        {eligibilityData.ageGroup && <div className="age-group-info" style={{ marginTop: '5px' }}>Age Group: {eligibilityData.ageGroup}</div>}
                                                    </motion.div>
                                                )}
                                                {eligibilityStep === 3 && (
                                                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                                                        <label style={{ marginBottom: '10px' }}>Gender:</label>
                                                        <div className="button-group wrap">
                                                            {['Male', 'Female', 'Other'].map(opt => (
                                                                <button key={opt} className={`option-btn ${eligibilityData.gender === opt ? 'active' : ''}`} onClick={() => handleOptionSelect('gender', opt, 3)}>{opt}</button>
                                                            ))}
                                                        </div>
                                                    </motion.div>
                                                )}
                                                {eligibilityStep === 4 && (
                                                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                                                        <label style={{ marginBottom: '10px' }}>Marital Status:</label>
                                                        <div className="button-group wrap">
                                                            {['Married', 'Unmarried', 'Single', 'Divorced', 'Widow/Widower'].map(opt => (
                                                                <button key={opt} className={`option-btn ${eligibilityData.maritalStatus === opt ? 'active' : ''}`} onClick={() => handleOptionSelect('maritalStatus', opt, 4)}>{opt}</button>
                                                            ))}
                                                        </div>
                                                    </motion.div>
                                                )}
                                                {eligibilityStep === 5 && (
                                                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                                                        <label style={{ marginBottom: '10px' }}>Which state do you live in?</label>
                                                        <select
                                                            value={eligibilityData.state}
                                                            onChange={e => {
                                                                const val = e.target.value;
                                                                setEligibilityData(prev => ({ ...prev, state: val }));
                                                                if (autoAdvanceTimeoutRef.current) clearTimeout(autoAdvanceTimeoutRef.current);
                                                                if (val) {
                                                                    autoAdvanceTimeoutRef.current = setTimeout(() => {
                                                                        setEligibilityStep(prev => prev === 5 ? prev + 1 : prev);
                                                                    }, 2000);
                                                                }
                                                            }}
                                                            className="form-input select"
                                                        >
                                                            <option value="">Select a state</option>
                                                            {indianStates.map(state => <option key={state} value={state}>{state}</option>)}
                                                        </select>
                                                    </motion.div>
                                                )}
                                                {eligibilityStep === 6 && (
                                                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                                                        <label style={{ marginBottom: '10px' }}>Occupation:</label>
                                                        <div className="button-group wrap">
                                                            {['Student', 'Farmer', 'Business', 'Self-employed', 'Government employee', 'Unemployed', 'Labour'].map(opt => (
                                                                <button key={opt} className={`option-btn ${eligibilityData.occupation === opt ? 'active' : ''}`} onClick={() => handleOptionSelect('occupation', opt, 6)}>{opt}</button>
                                                            ))}
                                                        </div>
                                                    </motion.div>
                                                )}
                                                {eligibilityStep === 7 && (
                                                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                                                        <label style={{ marginBottom: '10px' }}>Annual Income:</label>
                                                        <div className="button-group wrap">
                                                            {['Below ₹1 lakh', '₹1–3 lakh', '₹3–5 lakh', '₹5–8 lakh', 'Above ₹8 lakh'].map(opt => (
                                                                <button key={opt} className={`option-btn ${eligibilityData.income === opt ? 'active' : ''}`} onClick={() => handleOptionSelect('income', opt, 7)}>{opt}</button>
                                                            ))}
                                                        </div>
                                                    </motion.div>
                                                )}
                                                {eligibilityStep === 8 && (
                                                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                                                        <label style={{ marginBottom: '10px' }}>BPL / Ration Card Status:</label>
                                                        <div className="button-group wrap">
                                                            {['BPL card holder', 'APL', 'No ration card'].map(opt => (
                                                                <button key={opt} className={`option-btn ${eligibilityData.bplStatus === opt ? 'active' : ''}`} onClick={() => handleOptionSelect('bplStatus', opt, 8)}>{opt}</button>
                                                            ))}
                                                        </div>
                                                    </motion.div>
                                                )}
                                                {eligibilityStep === 9 && (
                                                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                                                        <label style={{ marginBottom: '10px' }}>Disability:</label>
                                                        <div className="button-group wrap">
                                                            {['Yes', 'No'].map(opt => (
                                                                <button key={opt} className={`option-btn ${eligibilityData.disability === opt ? 'active' : ''}`} onClick={() => handleOptionSelect('disability', opt, 9)}>{opt}</button>
                                                            ))}
                                                        </div>
                                                    </motion.div>
                                                )}
                                                {eligibilityStep === 10 && (
                                                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                                                        <label style={{ marginBottom: '10px' }}>Location Type:</label>
                                                        <div className="button-group wrap">
                                                            {['Rural', 'Urban'].map(opt => (
                                                                <button key={opt} className={`option-btn ${eligibilityData.locationType === opt ? 'active' : ''}`} onClick={() => setEligibilityData({ ...eligibilityData, locationType: opt })}>{opt}</button>
                                                            ))}
                                                        </div>
                                                    </motion.div>
                                                )}
                                            </div>

                                            <div className="modal-actions" style={{ justifyContent: eligibilityStep > 1 ? 'space-between' : 'flex-end' }}>
                                                {eligibilityStep > 1 && <button className="modal-btn secondary" onClick={() => setEligibilityStep(prev => prev - 1)}>Back</button>}
                                                {eligibilityStep < 10 ? (
                                                    <button
                                                        className="modal-btn primary"
                                                        onClick={() => setEligibilityStep(prev => prev + 1)}
                                                        disabled={
                                                            (eligibilityStep === 1 && !eligibilityData.name.trim()) ||
                                                            (eligibilityStep === 2 && !eligibilityData.age) ||
                                                            (eligibilityStep === 3 && !eligibilityData.gender) ||
                                                            (eligibilityStep === 4 && !eligibilityData.maritalStatus) ||
                                                            (eligibilityStep === 5 && !eligibilityData.state) ||
                                                            (eligibilityStep === 6 && !eligibilityData.occupation) ||
                                                            (eligibilityStep === 7 && !eligibilityData.income) ||
                                                            (eligibilityStep === 8 && !eligibilityData.bplStatus) ||
                                                            (eligibilityStep === 9 && !eligibilityData.disability)
                                                        }
                                                    >Next</button>
                                                ) : (
                                                    <button
                                                        className="modal-btn primary finish"
                                                        onClick={handleEligibilitySubmit}
                                                        disabled={!eligibilityData.locationType}
                                                    >Find Eligible Schemes</button>
                                                )}
                                            </div>
                                        </motion.div>
                                    </div>
                                )}
                            </AnimatePresence>
                            <div className="main-chat">

                                <div className="messages-container">
                                    {messages.length === 0 ? (
                                        <motion.div
                                            initial={{ opacity: 0, y: 20 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            className="welcome-card-wrapper"
                                        >
                                            <div className="avatar bot">
                                                🏛️
                                            </div>
                                            <div className="welcome-card">
                                                <h3>🙏 Jai Hind! Welcome to Sarkar Mitra</h3>
                                                <p>I am your dedicated AI assistant for <span className="highlight-text">Indian Government Schemes</span>.</p>
                                            </div>
                                        </motion.div>
                                    ) : (
                                        messages.map((msg, index) => (
                                            <motion.div
                                                key={index}
                                                initial={{ opacity: 0, y: 10 }}
                                                animate={{ opacity: 1, y: 0 }}
                                                className={`message-wrapper ${msg.role}`}
                                            >
                                                <div className={`avatar ${msg.role}`}>
                                                    {msg.role === 'assistant' ? '🏛️' : <User size={20} />}
                                                </div>
                                                <div className={`message-bubble ${msg.role}`}>
                                                    {msg.role === 'assistant' ? (
                                                        (() => {
                                                            const content = msg.content;
                                                            if (!content || typeof content !== 'string') {
                                                                return (
                                                                    <ReactMarkdown
                                                                        components={{
                                                                            ul: ({ node, ...props }) => <ul className="styled-list" {...props} />,
                                                                            ol: ({ node, ...props }) => <ol className="styled-list" {...props} />,
                                                                            a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />
                                                                        }}
                                                                    >
                                                                        {content}
                                                                    </ReactMarkdown>
                                                                );
                                                            }

                                                            let lastSchemeName = "";
                                                            const lines = content.split('\n');
                                                            const schemeList = [];

                                                            const processedContent = lines.map(line => {
                                                                const cleanLine = line.replace(/\*/g, '').replace(/^#{1,3}\s*/, '').trim();
                                                                const schemeMatch = cleanLine.match(/^(?:(\d{1,2})️⃣|\[NUMBER_EMOJI\])\s*(?:Scheme Name:\s*)?(.+)/i);

                                                                if (schemeMatch) {
                                                                    const num = schemeMatch[1] || "";
                                                                    lastSchemeName = schemeMatch[2].trim();
                                                                    schemeList.push({ number: num, name: lastSchemeName });
                                                                }

                                                                // Detect both old "(click me for details)" and new "📄 Click here for full details"
                                                                if (line.toLowerCase().includes('click me for details') || line.includes('📄 Click here for full details') || line.toLowerCase().includes('click here for full details')) {
                                                                    if (lastSchemeName) {
                                                                        // Prepend \n\n so button always starts on its own line, THEN convert to markdown link
                                                                        const converted = line
                                                                            .replace(/\(?click me for details\)?/gi, `[📄 Click here for full details](#detail-${encodeURIComponent(lastSchemeName)})`)
                                                                            .replace(/📄\s*Click here for full details/g, `[📄 Click here for full details](#detail-${encodeURIComponent(lastSchemeName)})`);
                                                                        return '\n\n' + converted;
                                                                    }
                                                                }
                                                                return line;
                                                            }).join('\n');

                                                            // Format roman numerals correctly — each as own paragraph (needed for hanging indent)
                                                            const finalContent = processedContent
                                                                // i), ii), iii) inline → \n\n so each becomes its own <p> (hanging indent needs separate <p>)
                                                                .replace(/([^\n])\s+(i{1,3}v?|iv|vi{0,3})\)/g, '$1\n\n$2)')
                                                                // Dot format: i. ii. iii.
                                                                .replace(/([^\n])\s+(i{1,3}v?|iv|vi{0,3})\.\s/g, '$1\n\n$2. ')
                                                                // Paragraph break specifically for A) and B) labels to ensure they are on new lines
                                                                .replace(/([^\n])\s*([A-D]\)\s)/g, '$1\n\n$2');

                                                            return (
                                                                <div className="assistant-msg-content" style={{ display: 'flex', flexDirection: 'column', gap: '0', width: '100%' }}>
                                                                    <ReactMarkdown
                                                                        components={{
                                                                            ul: ({ node, ...props }) => <ul className="styled-list" {...props} />,
                                                                            ol: ({ node, ...props }) => <ol className="styled-list" {...props} />,
                                                                            p: ({ node, children, ...props }) => {
                                                                                const text = Array.isArray(children)
                                                                                    ? String(children[0] || '')
                                                                                    : String(children || '');
                                                                                const trimmed = text.trim();

                                                                                const romanMatch = trimmed.match(/^(i{1,3}v?|iv|vi{0,3})\)\s+/i);
                                                                                const isSectionLabel = trimmed.match(/^[A-D]\)/);
                                                                                // Detect emoji headers or lines ending in a colon like "⭐ Key Features:"
                                                                                const isEmojiHeader = /^[\u{1F300}-\u{1F9FF}\u{2600}-\u{27BF}]/u.test(trimmed);
                                                                                const isTitleWithColon = trimmed.endsWith(':') && trimmed.length < 120;
                                                                                const isHeader = isTitleWithColon || isSectionLabel || isEmojiHeader;
                                                                                const isDescription = trimmed.length > 120;

                                                                                const childrenArray = React.Children.toArray(children);
                                                                                const hasButton = childrenArray.some(child => {
                                                                                    if (!child) return false;
                                                                                    if (child.type === 'a' && child.props && child.props.href && child.props.href.startsWith('#detail-')) return true;
                                                                                    if (child.props && child.props.className === 'details-custom-btn') return true;
                                                                                    const cText = typeof child === 'string' ? child : (child.props && typeof child.props.children === 'string' ? child.props.children : '');
                                                                                    return String(cText).includes('Click here for full details');
                                                                                });

                                                                                if (hasButton) {
                                                                                    let cleanedChildren = children;
                                                                                    if (romanMatch) {
                                                                                        if (typeof children === 'string') {
                                                                                            cleanedChildren = children.slice(romanMatch[0].length);
                                                                                        } else if (childrenArray.length > 0 && typeof childrenArray[0] === 'string') {
                                                                                            const firstCleaned = childrenArray[0].slice(romanMatch[0].length);
                                                                                            cleanedChildren = [firstCleaned, ...childrenArray.slice(1)];
                                                                                        }
                                                                                    }
                                                                                    return <p style={{ marginTop: '16px', marginBottom: '12px', paddingLeft: '4px', display: 'block' }} {...props}>{cleanedChildren}</p>;
                                                                                }

                                                                                if (isHeader) {
                                                                                    let cleanedHeader = children;
                                                                                    if (romanMatch) {
                                                                                        if (typeof children === 'string') {
                                                                                            cleanedHeader = children.slice(romanMatch[0].length);
                                                                                        } else if (childrenArray.length > 0 && typeof childrenArray[0] === 'string') {
                                                                                            const firstCleaned = childrenArray[0].slice(romanMatch[0].length);
                                                                                            cleanedHeader = [firstCleaned, ...childrenArray.slice(1)];
                                                                                        }
                                                                                    }
                                                                                    const headerStyle = {
                                                                                        color: 'var(--text-primary)',
                                                                                        marginTop: '2px',
                                                                                        marginBottom: '2px',
                                                                                        fontWeight: '400'
                                                                                    };

                                                                                    if (isSectionLabel && typeof cleanedHeader === 'string') {
                                                                                        const colonIndex = cleanedHeader.indexOf(':');
                                                                                        if (colonIndex !== -1) {
                                                                                            const labelPart = cleanedHeader.slice(0, colonIndex + 1);
                                                                                            const infoPart = cleanedHeader.slice(colonIndex + 1);
                                                                                            return (
                                                                                                <p className="assistant-header" style={headerStyle} {...props}>
                                                                                                    <strong style={{ fontWeight: '700' }}>{labelPart}</strong>
                                                                                                    {infoPart}
                                                                                                </p>
                                                                                            );
                                                                                        }
                                                                                    }
                                                                                    return <p className="assistant-header" style={{...headerStyle, fontWeight: isSectionLabel ? '700' : '400'}} {...props}>{cleanedHeader}</p>;
                                                                                }

                                                                                if (isDescription) {
                                                                                    return <p className="assistant-description" {...props}>{children}</p>;
                                                                                }

                                                                                if (romanMatch) {
                                                                                    let displayContent = children;
                                                                                    if (typeof children === 'string') {
                                                                                        displayContent = children.slice(romanMatch[0].length);
                                                                                    } else if (childrenArray.length > 0 && typeof childrenArray[0] === 'string') {
                                                                                        const firstCleaned = childrenArray[0].slice(romanMatch[0].length);
                                                                                        displayContent = [firstCleaned, ...childrenArray.slice(1)];
                                                                                    }
                                                                                    return (
                                                                                        <p className="assistant-list-item" {...props}>
                                                                                            <span className="roman-marker"></span>
                                                                                            <span style={{ flex: 1 }}>{displayContent}</span>
                                                                                        </p>
                                                                                    );
                                                                                }

                                                                                return (
                                                                                    <p className="assistant-paragraph" style={{ margin: '0 0 8px 0', paddingLeft: '4px' }} {...props}>
                                                                                        {children}
                                                                                    </p>
                                                                                );
                                                                            },
                                                                            a: ({ node, ...props }) => {
                                                                                if (props.href && props.href.startsWith('#detail-')) {
                                                                                    const schemeName = decodeURIComponent(props.href.replace('#detail-', ''));
                                                                                    return (
                                                                                        <button
                                                                                            className="details-custom-btn"
                                                                                            onClick={(e) => {
                                                                                                e.preventDefault();
                                                                                                sendMessage(null, `Tell me full details about ${schemeName}`);
                                                                                            }}
                                                                                            style={{
                                                                                                background: 'linear-gradient(135deg, #059669, #10b981)',
                                                                                                color: 'white',
                                                                                                border: 'none',
                                                                                                padding: '8px 16px',
                                                                                                borderRadius: '20px',
                                                                                                cursor: 'pointer',
                                                                                                fontSize: '14px',
                                                                                                fontWeight: 'bold',
                                                                                                marginTop: '10px',
                                                                                                boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
                                                                                                display: 'inline-flex',
                                                                                                alignItems: 'center',
                                                                                                gap: '6px',
                                                                                                transition: 'all 0.2s ease'
                                                                                            }}
                                                                                            onMouseEnter={(e) => { e.target.style.transform = 'scale(1.02)'; e.target.style.boxShadow = '0 6px 12px rgba(0,0,0,0.15)' }}
                                                                                            onMouseLeave={(e) => { e.target.style.transform = 'scale(1)'; e.target.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)' }}
                                                                                        >
                                                                                            📄 Click here for full details
                                                                                        </button>
                                                                                    );
                                                                                }
                                                                                return <a {...props} target="_blank" rel="noopener noreferrer" />;
                                                                            }
                                                                        }}
                                                                    >
                                                                        {finalContent}
                                                                    </ReactMarkdown>
                                                                    {schemeList.length > 1 && (
                                                                        <div className="scheme-quick-actions" style={{ marginTop: '10px', display: 'flex', gap: '8px', flexWrap: 'wrap', borderTop: '1px solid rgba(0,0,0,0.1)', paddingTop: '12px' }}>
                                                                            <div style={{ width: '100%', fontSize: '13px', fontWeight: 'bold', color: '#4b5563', marginBottom: '4px' }}>
                                                                                ⚡ Select a Scheme for Full Details:
                                                                            </div>
                                                                            {schemeList.map((scheme, i) => (
                                                                                <button
                                                                                    key={i}
                                                                                    onClick={(e) => { e.preventDefault(); sendMessage(null, `Tell me full details about ${scheme.name}`); }}
                                                                                    style={{
                                                                                        background: '#f3f4f6',
                                                                                        border: '1px solid #d1d5db',
                                                                                        padding: '6px 14px',
                                                                                        borderRadius: '16px',
                                                                                        color: '#1f2937',
                                                                                        fontSize: '14px',
                                                                                        fontWeight: '500',
                                                                                        cursor: 'pointer',
                                                                                        display: 'flex',
                                                                                        alignItems: 'center',
                                                                                        gap: '6px',
                                                                                        transition: 'all 0.2s ease',
                                                                                        boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
                                                                                    }}
                                                                                    onMouseEnter={(e) => { e.target.style.background = '#e5e7eb'; e.target.style.transform = 'translateY(-1px)'; }}
                                                                                    onMouseLeave={(e) => { e.target.style.background = '#f3f4f6'; e.target.style.transform = 'translateY(0)'; }}
                                                                                >
                                                                                    {scheme.number ? <span style={{ background: '#3b82f6', color: '#fff', borderRadius: '50%', width: '20px', height: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: 'bold' }}>{scheme.number}</span> : '👉'}
                                                                                    {scheme.name.length > 30 ? scheme.name.substring(0, 30) + '...' : scheme.name}
                                                                                </button>
                                                                            ))}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            );
                                                        })()
                                                    ) : (
                                                        msg.content
                                                    )}
                                                </div>
                                            </motion.div>
                                        ))
                                    )}

                                    {isLoading && (
                                        <motion.div
                                            initial={{ opacity: 0 }}
                                            animate={{ opacity: 1 }}
                                            className="message-wrapper assistant"
                                        >
                                            <div className="avatar bot">
                                                🏛️
                                            </div>
                                            <div className="message-bubble bot">
                                                <div className="typing-indicator">
                                                    <div className="typing-dot"></div>
                                                    <div className="typing-dot"></div>
                                                    <div className="typing-dot"></div>
                                                </div>
                                            </div>
                                        </motion.div>
                                    )}

                                    {showSuggestions && !isLoading && (
                                        <motion.div
                                            className="suggestions-grid"
                                            initial={{ opacity: 0, y: 20 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: 0.2 }}
                                        >
                                            {suggestions.map((item, idx) => (
                                                <button
                                                    key={idx}
                                                    className="suggestion-btn"
                                                    onClick={() => handleSuggestionClick(item.text)}
                                                >
                                                    <span>{item.icon}</span> {item.text}
                                                </button>
                                            ))}
                                        </motion.div>
                                    )}

                                    <div ref={messagesEndRef} style={{ height: 1 }} />
                                </div>

                                <div className="input-container">
                                    <div style={{ display: 'flex', justifyContent: 'center' }}>
                                        <button
                                            type="button"
                                            onClick={resetChat}
                                            className="reset-chat-btn"
                                            title="Clear conversation history"
                                        >
                                            <RotateCcw size={14} />
                                            {selectedLanguage === 'मराठी' ? 'चॅट रीसेट करा' : selectedLanguage === 'हिंदी' ? 'चैट रीसेट करें' : 'Reset Chat'}
                                        </button>
                                    </div>
                                    <div className="input-box">
                                        <form className="input-row" onSubmit={(e) => sendMessage(e)}>
                                            <textarea
                                                className="chat-input"
                                                placeholder={selectedLanguage === 'मराठी' ? 'कोणत्याही योजनेबद्दल विचारा...' : selectedLanguage === 'हिंदी' ? 'किसी भी योजना के बारे में पूछें...' : 'Ask about any scheme...'}
                                                value={input}
                                                onChange={(e) => setInput(e.target.value)}
                                                onKeyDown={(e) => {
                                                    if (e.key === 'Enter' && !e.shiftKey) {
                                                        e.preventDefault();
                                                        sendMessage(e);
                                                    }
                                                }}
                                                disabled={isLoading}
                                                rows={1}
                                            />

                                            <div className="input-actions" style={{ display: 'flex', alignItems: 'center', gap: '8px', paddingRight: '12px' }}>
                                                <button
                                                    type="button"
                                                    onClick={toggleListening}
                                                    title={isListening ? "Stop listening" : "Speak (uses selected language)"}
                                                    style={{
                                                        background: isListening ? 'rgba(244, 67, 54, 0.1)' : 'transparent',
                                                        border: 'none',
                                                        cursor: 'pointer',
                                                        padding: '8px',
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        justifyContent: 'center',
                                                        borderRadius: '50%',
                                                        color: isListening ? '#f44336' : '#9ba1a6',
                                                        transition: 'all 0.3s ease'
                                                    }}
                                                >
                                                    {isListening ? <MicOff size={20} /> : <Mic size={20} />}
                                                </button>

                                                <div style={{ position: 'relative' }}>
                                                    <button
                                                        type="button"
                                                        onClick={() => setShowLangMenu(!showLangMenu)}
                                                        title={`Click to change language. Current: ${selectedLanguage}`}
                                                        style={{
                                                            background: 'transparent',
                                                            border: '1px solid rgba(155, 161, 166, 0.5)',
                                                            cursor: 'pointer',
                                                            padding: '4px 8px',
                                                            borderRadius: '16px',
                                                            color: '#9ba1a6',
                                                            fontSize: '14px',
                                                            fontWeight: 'bold',
                                                            transition: 'all 0.3s ease',
                                                            userSelect: 'none'
                                                        }}
                                                    >
                                                        A/अ
                                                    </button>

                                                    <AnimatePresence>
                                                        {showLangMenu && (
                                                            <motion.div
                                                                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                                                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                                                exit={{ opacity: 0, scale: 0.95 }}
                                                                style={{
                                                                    position: 'absolute',
                                                                    bottom: 'calc(100% + 10px)',
                                                                    right: 0,
                                                                    background: '#ffffff',
                                                                    border: '1px solid var(--border-color)',
                                                                    borderRadius: '12px',
                                                                    padding: '8px 0',
                                                                    zIndex: 100,
                                                                    minWidth: '140px',
                                                                    boxShadow: '0 4px 20px rgba(0,0,0,0.08)'
                                                                }}
                                                            >
                                                                {['English', 'मराठी', 'हिंदी'].map(lang => (
                                                                    <div
                                                                        key={lang}
                                                                        onClick={() => { setSelectedLanguage(lang); setShowLangMenu(false); }}
                                                                        style={{
                                                                            padding: '10px 16px',
                                                                            cursor: 'pointer',
                                                                            color: selectedLanguage === lang ? 'var(--text-primary)' : 'var(--text-secondary)',
                                                                            background: selectedLanguage === lang ? 'rgba(0,0,0,0.03)' : 'transparent',
                                                                            transition: 'background 0.2s',
                                                                            display: 'flex',
                                                                            alignItems: 'center',
                                                                            justifyContent: 'space-between',
                                                                            fontSize: '14px',
                                                                            fontWeight: selectedLanguage === lang ? '600' : 'normal'
                                                                        }}
                                                                        onMouseEnter={(e) => e.target.style.background = 'rgba(0,0,0,0.05)'}
                                                                        onMouseLeave={(e) => e.target.style.background = selectedLanguage === lang ? 'rgba(0,0,0,0.03)' : 'transparent'}
                                                                    >
                                                                        {lang === 'हिंदी' ? 'हिंदी/Hindi' : lang}
                                                                        {selectedLanguage === lang && <span style={{ marginLeft: '8px' }}>✓</span>}
                                                                    </div>
                                                                ))}
                                                            </motion.div>
                                                        )}
                                                    </AnimatePresence>
                                                </div>

                                                <button
                                                    type="submit"
                                                    className="action-btn send"
                                                    style={{ marginLeft: '4px' }}
                                                    disabled={isLoading || (!input.trim() && !file) || isListening}
                                                >
                                                    <Send size={20} />
                                                </button>
                                            </div>
                                        </form>
                                    </div>

                                    <div className="disclaimer">
                                        <span className="info-icon">i</span>
                                        <span>Information is for awareness only. Always verify from official government websites. | <span className="sarkar-mitra-text">Sarkar Mitra</span> © 2026</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </>
    );
}

import ReactDOM from 'react-dom/client';

ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>
);
