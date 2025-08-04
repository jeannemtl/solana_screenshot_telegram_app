#!/usr/bin/env python3

import os
import time
import base64
import requests
import json
import re
import threading
import xml.etree.ElementTree as ET
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image
import subprocess
import tempfile
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote
import easyocr

class EnhancedScreenshotSummarizer:
    def __init__(self, api_key, telegram_bot_token=None, telegram_chat_id=None, screenshots_dir=None):
        self.api_key = api_key
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        # macOS default screenshot location
        self.screenshots_dir = screenshots_dir or os.path.expanduser('~/Desktop')
        self.processed_files = set()
        # Store data for button callbacks - keep for longer
        self.pending_analyses = {}
        self.last_update_id = 0
        # Add lock for thread safety
        self.callback_lock = threading.Lock()
        self.processing_callbacks = set()  # Track which callbacks are being processed
        
        # Track screenshot timing
        self.last_screenshot_time = None
        
        # Initialize OCR reader
        try:
            self.ocr_reader = easyocr.Reader(['en'])
            print("OCR initialized")
        except Exception as e:
            print(f"OCR initialization failed: {e}")
            self.ocr_reader = None
        
        # Start polling for button presses if Telegram is configured
        if self.telegram_bot_token:
            self.start_callback_polling()
    
    def format_time_since_last(self, current_time):
        """Format the time since last screenshot in a human-readable way"""
        if self.last_screenshot_time is None:
            return "first screenshot"
        
        time_diff = current_time - self.last_screenshot_time
        total_seconds = int(time_diff.total_seconds())
        
        if total_seconds < 60:
            return f"{total_seconds} seconds after last"
        elif total_seconds < 3600:  # Less than 1 hour
            minutes = total_seconds // 60
            if minutes == 1:
                return "1 minute after last"
            else:
                return f"{minutes} minutes after last"
        elif total_seconds < 86400:  # Less than 1 day
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            if hours == 1:
                if minutes == 0:
                    return "1 hour after last"
                else:
                    return f"1 hour {minutes}m after last"
            else:
                if minutes == 0:
                    return f"{hours} hours after last"
                else:
                    return f"{hours}h {minutes}m after last"
        else:  # 1 day or more
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            if days == 1:
                if hours == 0:
                    return "1 day after last"
                else:
                    return f"1 day {hours}h after last"
            else:
                if hours == 0:
                    return f"{days} days after last"
                else:
                    return f"{days}d {hours}h after last"
    
    def start_callback_polling(self):
        """Start polling for Telegram callback queries in a separate thread"""
        def poll():
            while True:
                try:
                    self.check_for_callbacks()
                    time.sleep(2)  # Check every 2 seconds
                except Exception as e:
                    print(f"Callback polling error: {e}")
                    time.sleep(5)
        
        polling_thread = threading.Thread(target=poll, daemon=True)
        polling_thread.start()
        print("Callback polling started")
    
    def check_for_callbacks(self):
        """Check for and handle Telegram callback queries"""
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/getUpdates"
            params = {"offset": self.last_update_id + 1, "timeout": 1}
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return
            
            data = response.json()
            if not data.get('ok') or not data.get('result'):
                return
            
            for update in data['result']:
                self.last_update_id = update['update_id']
                
                if 'callback_query' in update:
                    callback_query = update['callback_query']
                    callback_data = callback_query['data']
                    callback_id = callback_query['id']
                    
                    # Handle the callback
                    self.handle_callback(callback_data, callback_id)
                    
        except Exception as e:
            print(f"Error checking callbacks: {e}")
    
    def handle_callback(self, callback_data, callback_id):
        """Handle button press callbacks with improved logic"""
        try:
            # Answer the callback to remove loading state first
            requests.post(
                f"https://api.telegram.org/bot{self.telegram_bot_token}/answerCallbackQuery",
                data={"callback_query_id": callback_id}
            )
            
            print(f"Handling callback: {callback_data}")
            
            # Check if this callback is already being processed
            with self.callback_lock:
                if callback_data in self.processing_callbacks:
                    print(f"Callback {callback_data} already being processed, skipping")
                    return
                self.processing_callbacks.add(callback_data)
            
            try:
                # Extract analysis ID
                if callback_data.startswith("arxiv_research_"):
                    analysis_id = callback_data.replace("arxiv_research_", "")
                    action_type = "arxiv"
                elif callback_data.startswith("full_webpage_"):
                    analysis_id = callback_data.replace("full_webpage_", "")
                    action_type = "webpage"
                elif callback_data.startswith("deep_research_"):
                    analysis_id = callback_data.replace("deep_research_", "")
                    action_type = "deep_research"
                else:
                    print(f"Unknown callback data: {callback_data}")
                    return
                
                # Check if analysis data exists
                with self.callback_lock:
                    if analysis_id not in self.pending_analyses:
                        print(f"ERROR: Analysis ID {analysis_id} not found")
                        print(f"Available IDs: {list(self.pending_analyses.keys())}")
                        return
                    
                    analysis_data = self.pending_analyses[analysis_id]
                
                # Process the request
                if action_type == "arxiv":
                    print(f"Processing arXiv research for ID: {analysis_id}")
                    self.send_arxiv_research_summary(analysis_id)
                elif action_type == "webpage":
                    print(f"Processing webpage analysis for ID: {analysis_id}")
                    self.send_full_webpage_summary(analysis_id)
                elif action_type == "deep_research":
                    print(f"Processing deep research for ID: {analysis_id}")
                    self.send_deep_research_analysis(analysis_id)
                    
            finally:
                # Remove from processing set
                with self.callback_lock:
                    self.processing_callbacks.discard(callback_data)
                
        except Exception as e:
            print(f"Error handling callback: {e}")
            # Remove from processing set on error
            with self.callback_lock:
                self.processing_callbacks.discard(callback_data)
    
    def extract_research_keywords(self, image_path):
        """Extract potential research keywords from screenshot using AI"""
        try:
            with open(image_path, 'rb') as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            if image_path.lower().endswith('.png'):
                media_type = "image/png"
            elif image_path.lower().endswith(('.jpg', '.jpeg')):
                media_type = "image/jpeg"
            else:
                media_type = "image/png"
            
            keyword_prompt = """Analyze this screenshot and extract potential research keywords or academic topics. Look for:

1. Technical terms, algorithms, or methodologies
2. Scientific concepts or theories
3. Research domains or fields
4. Mathematical concepts or formulas
5. Technology or software names

Respond with:
KEYWORDS: [comma-separated list of 3-7 relevant research keywords]
IS_RESEARCH: [yes/no - whether this appears to be research-related content]
FIELD: [primary research field if identifiable, e.g., machine learning, physics, biology]"""
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 200,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": keyword_prompt
                                },
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_data
                                    }
                                }
                            ]
                        }
                    ]
                }
            )
            
            if response.status_code == 200:
                analysis = response.json()['content'][0]['text']
                return self.parse_keyword_analysis(analysis)
            else:
                return None
                
        except Exception as e:
            print(f"Keyword extraction failed: {e}")
            return None
    
    def parse_keyword_analysis(self, analysis_text):
        """Parse keyword analysis response"""
        result = {
            'is_research': False,
            'keywords': [],
            'field': 'unknown'
        }
        
        try:
            lines = analysis_text.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('KEYWORDS:'):
                    keywords_str = line.split(':', 1)[1].strip()
                    result['keywords'] = [k.strip() for k in keywords_str.split(',')]
                elif line.startswith('IS_RESEARCH:'):
                    result['is_research'] = 'yes' in line.lower()
                elif line.startswith('FIELD:'):
                    result['field'] = line.split(':', 1)[1].strip()
        
        except Exception as e:
            print(f"Keyword parsing failed: {e}")
        
        return result
    
    def search_arxiv_papers(self, keywords, max_results=5):
        """Search arXiv papers using keywords"""
        try:
            # Construct search query
            search_terms = ' AND '.join(keywords[:3])  # Use first 3 keywords
            query = quote(search_terms)
            
            url = f"http://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results={max_results}&sortBy=relevance&sortOrder=descending"
            
            print(f"Searching arXiv for: {search_terms}")
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # Parse XML response
            root = ET.fromstring(response.content)
            
            papers = []
            for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                paper = {}
                
                # Extract basic info
                paper['id'] = entry.find('{http://www.w3.org/2005/Atom}id').text
                paper['title'] = entry.find('{http://www.w3.org/2005/Atom}title').text.strip()
                paper['summary'] = entry.find('{http://www.w3.org/2005/Atom}summary').text.strip()
                
                # Extract authors
                authors = []
                for author in entry.findall('{http://www.w3.org/2005/Atom}author'):
                    name = author.find('{http://www.w3.org/2005/Atom}name').text
                    authors.append(name)
                paper['authors'] = authors
                
                # Extract published date
                published = entry.find('{http://www.w3.org/2005/Atom}published').text
                paper['published'] = published[:10]  # Just the date part
                
                # Extract categories
                categories = []
                for category in entry.findall('{http://arxiv.org/schemas/atom}primary_category'):
                    categories.append(category.get('term'))
                paper['categories'] = categories
                
                papers.append(paper)
            
            return papers
            
        except Exception as e:
            print(f"arXiv search failed: {e}")
            return []
    
    def send_arxiv_research_summary(self, analysis_id):
        """Send arXiv research analysis"""
        print(f"=== arXiv Research Analysis Started ===")
        
        # Get analysis data with lock
        with self.callback_lock:
            if analysis_id not in self.pending_analyses:
                print(f"ERROR: Analysis ID {analysis_id} not found")
                return
            analysis_data = self.pending_analyses[analysis_id]
        
        image_path = analysis_data['image_path']
        print(f"Image path: {image_path}")
        
        # Extract research keywords from screenshot
        print("Extracting research keywords...")
        keyword_analysis = self.extract_research_keywords(image_path)
        
        if not keyword_analysis:
            print("ERROR: Failed to extract keywords")
            message = "*arXiv Research Analysis*\n\nFailed to analyze screenshot for research content."
        elif not keyword_analysis['is_research']:
            print("Not research content")
            message = "*arXiv Research Analysis*\n\nThis screenshot doesn't appear to contain research-related content."
        else:
            print(f"Research content detected. Keywords: {keyword_analysis['keywords']}")
            # Search arXiv for related papers
            papers = self.search_arxiv_papers(keyword_analysis['keywords'])
            
            if not papers:
                print("No papers found")
                message = f"*arXiv Research Analysis*\n\nNo related papers found for keywords: {', '.join(keyword_analysis['keywords'])}"
            else:
                print(f"Found {len(papers)} papers")
                # Format research summary
                message = f"*arXiv Research Analysis*\n\n"
                message += f"**Research Field**: {keyword_analysis['field']}\n"
                message += f"**Keywords**: {', '.join(keyword_analysis['keywords'][:5])}\n\n"
                message += f"**Related Papers ({len(papers)} found):**\n\n"
                
                for i, paper in enumerate(papers[:3], 1):  # Show top 3 papers
                    authors_str = ', '.join(paper['authors'][:2])
                    if len(paper['authors']) > 2:
                        authors_str += f" et al."
                    
                    # Truncate title and summary for Telegram
                    title = paper['title'][:80] + "..." if len(paper['title']) > 80 else paper['title']
                    summary = paper['summary'][:150] + "..." if len(paper['summary']) > 150 else paper['summary']
                    
                    message += f"**{i}. {title}**\n"
                    message += f"Authors: {authors_str}\n"
                    message += f"Published: {paper['published']}\n"
                    message += f"Summary: {summary}\n"
                    message += f"Link: {paper['id']}\n\n"
        
        # Send the message
        print(f"Sending message of length: {len(message)}")
        if len(message) > 4000:
            # Send in parts
            parts = self.split_message(message, 4000)
            for i, part in enumerate(parts):
                print(f"Sending part {i+1}/{len(parts)}")
                self.send_telegram_message(part)
                time.sleep(1)  # Avoid rate limiting
        else:
            self.send_telegram_message(message)
        
        print("=== arXiv Research Analysis Complete ===\n")
    
    def send_deep_research_analysis(self, analysis_id):
        """Perform comprehensive deep research analysis"""
        print(f"=== Deep Research Analysis Started ===")
        
        # Get analysis data with lock
        with self.callback_lock:
            if analysis_id not in self.pending_analyses:
                print(f"ERROR: Analysis ID {analysis_id} not found")
                return
            analysis_data = self.pending_analyses[analysis_id]
        
        image_path = analysis_data['image_path']
        print(f"Image path: {image_path}")
        
        # Send initial "research in progress" message
        self.send_telegram_message("🔬 *Deep Research Analysis*\n\nAnalyzing screenshot and conducting comprehensive research...\n\n⏳ This may take 1-2 minutes")
        
        # Step 1: Extract comprehensive research topics
        print("Step 1: Extracting research topics...")
        research_topics = self.extract_comprehensive_topics(image_path)
        
        if not research_topics:
            message = "*Deep Research Analysis*\n\nFailed to extract research topics from screenshot."
            self.send_telegram_message(message)
            return
        
        # Step 2: Generate research questions
        print("Step 2: Generating research questions...")
        research_questions = self.generate_research_questions(research_topics)
        
        # Step 3: Conduct multi-source research
        print("Step 3: Conducting multi-source research...")
        research_results = self.conduct_multi_source_research(research_topics, research_questions)
        
        # Step 4: Synthesize comprehensive analysis
        print("Step 4: Synthesizing comprehensive analysis...")
        final_analysis = self.synthesize_research_findings(research_topics, research_questions, research_results, analysis_data)
        
        # Send final comprehensive report
        message = f"🔬 *Deep Research Analysis Complete*\n\n{final_analysis}"
        
        # Send in parts if too long
        if len(message) > 4000:
            parts = self.split_message(message, 4000)
            for i, part in enumerate(parts):
                print(f"Sending research part {i+1}/{len(parts)}")
                self.send_telegram_message(part)
                time.sleep(1)
        else:
            self.send_telegram_message(message)
        
        print("=== Deep Research Analysis Complete ===\n")
    
    def extract_comprehensive_topics(self, image_path):
        """Extract comprehensive research topics and context"""
        try:
            with open(image_path, 'rb') as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            if image_path.lower().endswith('.png'):
                media_type = "image/png"
            elif image_path.lower().endswith(('.jpg', '.jpeg')):
                media_type = "image/jpeg"
            else:
                media_type = "image/png"
            
            prompt = """Analyze this screenshot comprehensively and extract all research-worthy topics. Look for:

1. Main subject/technology/concept being discussed
2. Related technologies, frameworks, or methodologies
3. Potential research areas and sub-topics
4. Key terms that could lead to deeper investigation
5. Context clues about the domain or field
6. Any specific problems or challenges mentioned
7. Names of people, companies, or projects referenced

Respond with:
MAIN_TOPIC: [primary subject of the screenshot]
RELATED_TOPICS: [comma-separated list of related research areas]
TECHNICAL_TERMS: [comma-separated list of technical terms and concepts]
DOMAIN: [field/industry/domain]
RESEARCH_POTENTIAL: [high/medium/low - how much research potential this has]
CONTEXT: [brief description of what type of content this is]"""
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 400,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                },
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_data
                                    }
                                }
                            ]
                        }
                    ]
                }
            )
            
            if response.status_code == 200:
                analysis = response.json()['content'][0]['text']
                return self.parse_comprehensive_topics(analysis)
            else:
                return None
                
        except Exception as e:
            print(f"Topic extraction failed: {e}")
            return None
    
    def parse_comprehensive_topics(self, analysis_text):
        """Parse comprehensive topic analysis"""
        result = {
            'main_topic': '',
            'related_topics': [],
            'technical_terms': [],
            'domain': '',
            'research_potential': 'medium',
            'context': ''
        }
        
        try:
            lines = analysis_text.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('MAIN_TOPIC:'):
                    result['main_topic'] = line.split(':', 1)[1].strip()
                elif line.startswith('RELATED_TOPICS:'):
                    topics = line.split(':', 1)[1].strip()
                    result['related_topics'] = [t.strip() for t in topics.split(',')]
                elif line.startswith('TECHNICAL_TERMS:'):
                    terms = line.split(':', 1)[1].strip()
                    result['technical_terms'] = [t.strip() for t in terms.split(',')]
                elif line.startswith('DOMAIN:'):
                    result['domain'] = line.split(':', 1)[1].strip()
                elif line.startswith('RESEARCH_POTENTIAL:'):
                    result['research_potential'] = line.split(':', 1)[1].strip()
                elif line.startswith('CONTEXT:'):
                    result['context'] = line.split(':', 1)[1].strip()
        except Exception as e:
            print(f"Topic parsing failed: {e}")
        
        return result
    
    def generate_research_questions(self, topics):
        """Generate focused research questions based on topics"""
        try:
            prompt = f"""Based on these research topics, generate 5-7 focused research questions that would provide deep insights:

MAIN TOPIC: {topics['main_topic']}
DOMAIN: {topics['domain']}
RELATED TOPICS: {', '.join(topics['related_topics'][:5])}
TECHNICAL TERMS: {', '.join(topics['technical_terms'][:5])}

Generate questions that explore:
1. Current state of the art
2. Recent developments and trends
3. Practical applications and use cases
4. Challenges and limitations
5. Future directions and opportunities
6. Comparative analysis with alternatives
7. Real-world implementation examples

Format as:
QUESTION_1: [specific research question]
QUESTION_2: [specific research question]
...etc"""
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 500,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ]
                }
            )
            
            if response.status_code == 200:
                response_text = response.json()['content'][0]['text']
                questions = []
                for line in response_text.split('\n'):
                    if line.strip().startswith('QUESTION_'):
                        question = line.split(':', 1)[1].strip()
                        questions.append(question)
                return questions
            else:
                return []
                
        except Exception as e:
            print(f"Question generation failed: {e}")
            return []
    
    def conduct_multi_source_research(self, topics, questions):
        """Conduct research using multiple approaches"""
        results = {
            'arxiv_papers': [],
            'web_research': [],
            'technical_analysis': ''
        }
        
        # 1. Search arXiv if research-related
        if topics['research_potential'] in ['high', 'medium']:
            print("Searching arXiv papers...")
            all_keywords = topics['technical_terms'] + topics['related_topics']
            results['arxiv_papers'] = self.search_arxiv_papers(all_keywords[:5], max_results=10)
        
        # 2. Conduct web research for each key question
        print("Conducting web research...")
        search_queries = []
        
        # Generate search queries from topics and questions
        search_queries.append(f"{topics['main_topic']} latest developments 2024")
        search_queries.append(f"{topics['main_topic']} {topics['domain']} applications")
        search_queries.append(f"{topics['main_topic']} challenges limitations")
        
        # Add question-based searches
        for question in questions[:3]:  # Use top 3 questions
            query = self.question_to_search_query(question, topics['main_topic'])
            if query:
                search_queries.append(query)
        
        # Simulate web research (in real implementation, you'd use SerpAPI or similar)
        for query in search_queries[:5]:  # Limit to 5 searches
            results['web_research'].append({
                'query': query,
                'summary': f"Research findings for: {query}"  # Placeholder
            })
        
        # 3. Generate technical analysis
        print("Generating technical analysis...")
        results['technical_analysis'] = self.generate_technical_analysis(topics)
        
        return results
    
    def question_to_search_query(self, question, main_topic):
        """Convert research question to search query"""
        # Simple extraction of key terms from question
        question_lower = question.lower()
        if 'current state' in question_lower or 'state of art' in question_lower:
            return f"{main_topic} state of the art 2024"
        elif 'challenge' in question_lower or 'limitation' in question_lower:
            return f"{main_topic} challenges problems"
        elif 'application' in question_lower or 'use case' in question_lower:
            return f"{main_topic} applications use cases"
        elif 'future' in question_lower or 'trend' in question_lower:
            return f"{main_topic} future trends 2024"
        else:
            return f"{main_topic} research"
    
    def generate_technical_analysis(self, topics):
        """Generate deep technical analysis"""
        try:
            prompt = f"""Provide a comprehensive technical analysis of {topics['main_topic']} in the {topics['domain']} domain.

Cover:
1. Technical architecture and components
2. Key algorithms or methodologies involved
3. Performance characteristics and metrics
4. Integration considerations
5. Scalability and limitations
6. Comparison with alternative approaches
7. Implementation complexity and requirements

MAIN TOPIC: {topics['main_topic']}
DOMAIN: {topics['domain']}
TECHNICAL TERMS: {', '.join(topics['technical_terms'][:7])}
RELATED AREAS: {', '.join(topics['related_topics'][:5])}

Provide a detailed technical analysis suitable for researchers and practitioners."""
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 800,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ]
                }
            )
            
            if response.status_code == 200:
                return response.json()['content'][0]['text']
            else:
                return "Technical analysis generation failed"
                
        except Exception as e:
            print(f"Technical analysis failed: {e}")
            return f"Error generating technical analysis: {str(e)}"
    
    def synthesize_research_findings(self, topics, questions, results, analysis_data):
        """Synthesize all research findings into comprehensive report"""
        try:
            # Prepare research context
            arxiv_summary = ""
            if results['arxiv_papers']:
                arxiv_summary = f"Found {len(results['arxiv_papers'])} relevant papers on arXiv:\n"
                for i, paper in enumerate(results['arxiv_papers'][:3], 1):
                    arxiv_summary += f"{i}. {paper['title'][:60]}... ({paper['published']})\n"
            
            webpage_context = ""
            if analysis_data.get('webpage_data') and analysis_data['webpage_data']['success']:
                webpage_context = f"Source webpage: {analysis_data['webpage_data']['title']}"
            
            prompt = f"""Synthesize a comprehensive research report based on the following analysis:

SCREENSHOT CONTEXT: {topics['context']}
MAIN RESEARCH TOPIC: {topics['main_topic']}
DOMAIN: {topics['domain']}
RESEARCH POTENTIAL: {topics['research_potential']}

TECHNICAL ANALYSIS:
{results['technical_analysis']}

ARXIV RESEARCH:
{arxiv_summary}

WEBPAGE CONTEXT:
{webpage_context}

Generate a comprehensive report covering:
1. **Executive Summary** - Key findings and insights
2. **Technical Overview** - Core concepts and technologies
3. **Current State** - What's happening now in this field
4. **Key Insights** - Important discoveries or patterns
5. **Future Directions** - Where this field is heading
6. **Practical Applications** - Real-world use cases
7. **Further Research** - Recommended next steps

Keep it detailed but well-organized. Use markdown formatting for sections."""
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1500,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ]
                }
            )
            
            if response.status_code == 200:
                return response.json()['content'][0]['text']
            else:
                return "Research synthesis failed"
                
        except Exception as e:
            print(f"Research synthesis failed: {e}")
            return f"Error synthesizing research: {str(e)}"
    
    def split_message(self, message, max_length):
        """Split long message into parts"""
        parts = []
        current_part = ""
        
        for line in message.split('\n'):
            if len(current_part) + len(line) + 1 <= max_length:
                current_part += line + '\n'
            else:
                if current_part:
                    parts.append(current_part.strip())
                current_part = line + '\n'
        
        if current_part:
            parts.append(current_part.strip())
        
        return parts
    
    def send_full_webpage_summary(self, analysis_id):
        """Send full webpage summary"""
        print(f"=== Full Webpage Analysis Started ===")
        
        # Get analysis data with lock
        with self.callback_lock:
            if analysis_id not in self.pending_analyses:
                print(f"ERROR: Analysis ID {analysis_id} not found")
                return
            analysis_data = self.pending_analyses[analysis_id]
        
        if analysis_data.get('webpage_data') and analysis_data['webpage_data']['success']:
            webpage_data = analysis_data['webpage_data']
            print(f"Getting full webpage summary for: {webpage_data['title']}")
            full_summary = self.get_full_webpage_summary(webpage_data)
            
            message = f"*Full Webpage Analysis*\n\n**Title**: {webpage_data['title']}\n**URL**: {webpage_data['url']}\n\n{full_summary}"
        else:
            print("No webpage data available")
            message = "*Full Webpage Analysis*\n\nNo webpage content available for this screenshot."
        
        print(f"Sending webpage analysis message of length: {len(message)}")
        self.send_telegram_message(message)
        
        print("=== Full Webpage Analysis Complete ===\n")
    
    def get_brief_summary(self, image_path):
        """Get brief initial summary of screenshot"""
        try:
            with open(image_path, 'rb') as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            if image_path.lower().endswith('.png'):
                media_type = "image/png"
            elif image_path.lower().endswith(('.jpg', '.jpeg')):
                media_type = "image/jpeg"
            else:
                media_type = "image/png"
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 100,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Provide a very brief 1-2 sentence summary of what's shown in this screenshot."
                                },
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_data
                                    }
                                }
                            ]
                        }
                    ]
                }
            )
            
            if response.status_code == 200:
                return response.json()['content'][0]['text']
            else:
                return f"Error: {response.status_code}"
                
        except Exception as e:
            return f"Error: {str(e)}"
    
    def get_full_webpage_summary(self, webpage_data):
        """Get comprehensive summary of full webpage content"""
        try:
            prompt = f"""Analyze this complete webpage content and provide a comprehensive summary.

WEBPAGE TITLE: {webpage_data['title']}
WEBPAGE CONTENT: {webpage_data['content'][:5000]}

Provide:
1. Main topic and purpose of the page
2. Key sections and their content
3. Important details, facts, or data mentioned
4. Target audience and use cases
5. Any notable features or functionality

Keep it detailed but well-organized."""
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 500,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ]
                }
            )
            
            if response.status_code == 200:
                return response.json()['content'][0]['text']
            else:
                return f"Error: {response.status_code}"
                
        except Exception as e:
            return f"Error: {str(e)}"
    
    def extract_urls_from_screenshot(self, image_path):
        """Extract URLs from screenshot using OCR"""
        urls = []
        
        if not self.ocr_reader:
            return urls
            
        try:
            # Use OCR to extract text
            results = self.ocr_reader.readtext(image_path)
            
            # Extract text and look for URLs
            text_content = ' '.join([result[1] for result in results])
            
            # URL patterns
            url_patterns = [
                r'https?://[^\s<>"{}|\\^`\[\]]+',
                r'www\.[^\s<>"{}|\\^`\[\]]+',
                r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?'
            ]
            
            for pattern in url_patterns:
                matches = re.findall(pattern, text_content, re.IGNORECASE)
                for match in matches:
                    clean_url = match.strip('.,;:!?')
                    if not clean_url.startswith('http'):
                        clean_url = 'https://' + clean_url
                    urls.append(clean_url)
            
            urls = list(dict.fromkeys(urls))
            
            if urls:
                print(f"Found URLs in screenshot: {urls[:3]}...")
            
            return urls
            
        except Exception as e:
            print(f"URL extraction failed: {e}")
            return urls
    
    def analyze_screenshot_for_webpage(self, image_path):
        """Use AI to analyze if screenshot is from a webpage and extract URLs"""
        try:
            with open(image_path, 'rb') as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            if image_path.lower().endswith('.png'):
                media_type = "image/png"
            elif image_path.lower().endswith(('.jpg', '.jpeg')):
                media_type = "image/jpeg"
            else:
                media_type = "image/png"
            
            analysis_prompt = """Analyze this screenshot and determine:

1. Is this a webpage/website screenshot? (yes/no)
2. If yes, what is the likely URL or domain visible in the image?
3. Can you see any URLs in address bars, links, or references?
4. What type of website is this (news, blog, e-commerce, social media, etc.)?

Please respond in this exact format:
WEBPAGE: [yes/no]
URL: [extracted URL or "none found"]
DOMAIN: [domain if identifiable or "unknown"]
TYPE: [website type or "unknown"]
SUMMARY: [brief description of what's shown]"""
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 300,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": analysis_prompt
                                },
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_data
                                    }
                                }
                            ]
                        }
                    ]
                }
            )
            
            if response.status_code == 200:
                analysis = response.json()['content'][0]['text']
                return self.parse_analysis(analysis)
            else:
                return None
                
        except Exception as e:
            print(f"AI analysis failed: {e}")
            return None
    
    def parse_analysis(self, analysis_text):
        """Parse the AI analysis response"""
        result = {
            'is_webpage': False,
            'url': None,
            'domain': None,
            'type': 'unknown',
            'summary': analysis_text
        }
        
        try:
            lines = analysis_text.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('WEBPAGE:'):
                    result['is_webpage'] = 'yes' in line.lower()
                elif line.startswith('URL:'):
                    url = line.split(':', 1)[1].strip()
                    if url != "none found" and url != "unknown":
                        result['url'] = url
                elif line.startswith('DOMAIN:'):
                    domain = line.split(':', 1)[1].strip()
                    if domain != "unknown":
                        result['domain'] = domain
                elif line.startswith('TYPE:'):
                    result['type'] = line.split(':', 1)[1].strip()
                elif line.startswith('SUMMARY:'):
                    result['summary'] = line.split(':', 1)[1].strip()
        
        except Exception as e:
            print(f"Analysis parsing failed: {e}")
        
        return result
    
    def fetch_webpage_content(self, url):
        """Fetch and extract text content from webpage"""
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            print(f"Fetching webpage: {url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "aside"]):
                script.decompose()
            
            # Extract title
            title = soup.find('title')
            title_text = title.get_text().strip() if title else "No title found"
            
            # Extract main content
            content_selectors = [
                'main', 'article', '.content', '#content', '.post', '.entry',
                '.article-body', '.story-body', '.post-content'
            ]
            
            main_content = None
            for selector in content_selectors:
                element = soup.select_one(selector)
                if element:
                    main_content = element
                    break
            
            if not main_content:
                main_content = soup.find('body')
            
            if main_content:
                text_content = main_content.get_text()
            else:
                text_content = soup.get_text()
            
            # Clean up text
            lines = (line.strip() for line in text_content.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = ' '.join(chunk for chunk in chunks if chunk)
            
            if len(clean_text) > 8000:
                clean_text = clean_text[:8000] + "... [content truncated]"
            
            return {
                'title': title_text,
                'content': clean_text,
                'url': url,
                'success': True
            }
            
        except Exception as e:
            print(f"Failed to fetch webpage: {e}")
            return {
                'title': None,
                'content': None,
                'url': url,
                'success': False,
                'error': str(e)
            }
    
    def escape_markdown(self, text):
        """Escape special characters for Telegram Markdown"""
        # Characters that need to be escaped in Telegram Markdown
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        
        return text
    
    def send_telegram_message(self, message):
        """Send message to Telegram with proper markdown escaping"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("Telegram not configured - skipping message")
            return False
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            
            # First try with Markdown
            data = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                print("Message sent to Telegram")
                return True
            elif "can't parse entities" in response.text.lower():
                print("Markdown parsing failed, trying without formatting...")
                # Fallback: send without markdown formatting
                data["parse_mode"] = None
                # Remove markdown formatting characters
                clean_message = re.sub(r'[*_`]', '', message)
                data["text"] = clean_message
                
                response = requests.post(url, data=data, timeout=10)
                
                if response.status_code == 200:
                    print("Message sent to Telegram (plain text)")
                    return True
                else:
                    print(f"Telegram API error: {response.status_code} - {response.text}")
                    return False
            else:
                print(f"Telegram API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Failed to send Telegram message: {str(e)}")
            return False
    
    def send_telegram_photo_with_buttons(self, image_path, brief_summary, analysis_id, has_webpage=False, current_time=None):
        """Send photo with brief summary and action buttons"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("Telegram not configured - skipping photo")
            return False
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendPhoto"
            
            # Use provided time or current time
            if current_time is None:
                current_time = datetime.now()
            
            timestamp = current_time.strftime('%H:%M:%S')
            time_since_last = self.format_time_since_last(current_time)
            
            caption = f"*Screenshot Summary* _{time_since_last}_\n\n{brief_summary}\n\n_Captured: {timestamp}_"
            
            # Create inline keyboard
            buttons = [
                [
                    {
                        "text": "🔬 Research Papers",
                        "callback_data": f"arxiv_research_{analysis_id}"
                    }
                ],
                [
                    {
                        "text": "🧠 Deep Research",
                        "callback_data": f"deep_research_{analysis_id}"
                    }
                ]
            ]
            
            if has_webpage:
                buttons.append([
                    {
                        "text": "🌐 Webpage Content", 
                        "callback_data": f"full_webpage_{analysis_id}"
                    }
                ])
            else:
                # If no webpage, still show Deep Research as option
                pass
            
            reply_markup = {
                "inline_keyboard": buttons
            }
            
            with open(image_path, 'rb') as photo:
                files = {'photo': photo}
                data = {
                    'chat_id': self.telegram_chat_id,
                    'caption': caption,
                    'parse_mode': 'Markdown',
                    'reply_markup': json.dumps(reply_markup)
                }
                
                response = requests.post(url, files=files, data=data, timeout=30)
            
            if response.status_code == 200:
                print("Photo with buttons sent to Telegram")
                return True
            else:
                print(f"Telegram photo API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Failed to send photo to Telegram: {str(e)}")
            return False
    
    def save_summary(self, image_path, summary, webpage_data=None):
        """Save summary to a text file next to the image"""
        base_name = os.path.splitext(image_path)[0]
        summary_path = f"{base_name}_summary.txt"
        
        with open(summary_path, 'w') as f:
            f.write(f"Screenshot: {os.path.basename(image_path)}\n")
            f.write(f"Processed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if webpage_data and webpage_data['success']:
                f.write(f"Webpage URL: {webpage_data['url']}\n")
                f.write(f"Webpage Title: {webpage_data['title']}\n")
                f.write("Type: Enhanced webpage analysis\n")
            else:
                f.write("Type: Screenshot-only analysis\n")
            f.write(f"\nSummary:\n{summary}\n")
        
        return summary_path
    
    def cleanup_old_analyses(self):
        """Clean up old analysis data, keeping only recent ones"""
        with self.callback_lock:
            if len(self.pending_analyses) > 10:  # Keep more analyses
                # Sort by timestamp (analysis_id is timestamp)
                sorted_ids = sorted(self.pending_analyses.keys(), key=int)
                # Remove oldest half
                to_remove = sorted_ids[:len(sorted_ids)//2]
                for analysis_id in to_remove:
                    del self.pending_analyses[analysis_id]
                print(f"Cleaned up {len(to_remove)} old analyses")

class ScreenshotHandler(FileSystemEventHandler):
    def __init__(self, summarizer):
        self.summarizer = summarizer
        super().__init__()
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        filepath = event.src_path
        filename = os.path.basename(filepath)
        
        print(f"=== FILE WATCHER EVENT ===")
        print(f"New file detected: {filename}")
        print(f"Full path: {filepath}")
        print(f"File extension: {os.path.splitext(filename)[1]}")
        
        # Skip non-image files explicitly
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            print(f"SKIPPING: Non-image file: {filename}")
            return
        
        # Skip summary files but allow screenshot files that start with dot
        if '_summary' in filename.lower():
            print(f"SKIPPING: Summary file: {filename}")
            return
        
        # Skip if already processed
        if filepath in self.summarizer.processed_files:
            print(f"SKIPPING: Already processed: {filename}")
            return
        
        is_screenshot = (
            'screenshot' in filename.lower() or 
            'screen shot' in filename.lower() or
            filename.startswith('Screenshot') or 
            filename.startswith('Screen Shot') or
            filename.startswith('.Screenshot') or  # macOS sometimes creates these
            'CleanShot' in filename
        )
        
        print(f"Is screenshot: {is_screenshot}")
        
        if is_screenshot:
            self.summarizer.processed_files.add(filepath)
            print(f"PROCESSING: {filename}")
            print(f"Total processed files: {len(self.summarizer.processed_files)}")
            time.sleep(2)
            self.process_screenshot(filepath)
        else:
            print(f"NOT PROCESSING: {filename} (not identified as screenshot)")
        
        print(f"=== FILE WATCHER EVENT END ===\n")
    
    def process_screenshot(self, filepath):
        """Process a new screenshot with enhanced analysis options"""
        print(f"Processing screenshot: {os.path.basename(filepath)}")
        
        # Record current time and update last screenshot time
        current_time = datetime.now()
        
        # Clean up old analyses less aggressively
        self.summarizer.cleanup_old_analyses()
        
        directory = os.path.dirname(filepath)
        
        try:
            all_files = os.listdir(directory)
            matching_files = [f for f in all_files if ('Screenshot' in f or f.startswith('.Screenshot')) and f.endswith('.png')]
            
            if matching_files:
                matching_files.sort(key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)
                actual_filepath = os.path.join(directory, matching_files[0])
                print(f"Using actual file: {matching_files[0]}")
            else:
                actual_filepath = filepath
                
        except Exception as e:
            print(f"Error finding file: {e}")
            actual_filepath = filepath
        
        # Wait for file to be ready
        max_retries = 3
        for i in range(max_retries):
            if os.path.exists(actual_filepath) and os.path.getsize(actual_filepath) > 0:
                break
            print(f"Waiting for file to be ready... ({i+1}/{max_retries})")
            time.sleep(1)
        
        if not os.path.exists(actual_filepath):
            print(f"File not found: {actual_filepath}")
            return
        
        # Generate unique analysis ID
        analysis_id = str(int(time.time() * 1000))  # Use milliseconds for better uniqueness
        
        # Step 1: Get brief summary
        print("Getting brief summary...")
        brief_summary = self.summarizer.get_brief_summary(actual_filepath)
        
        # Step 2: Analyze for webpage content
        print("Analyzing for webpage content...")
        analysis = self.summarizer.analyze_screenshot_for_webpage(actual_filepath)
        ocr_urls = self.summarizer.extract_urls_from_screenshot(actual_filepath)
        
        # Step 3: Fetch webpage if detected
        webpage_data = None
        target_url = None
        has_webpage = False
        
        if analysis and analysis['is_webpage']:
            print("Detected webpage screenshot")
            has_webpage = True
            
            if analysis['url']:
                target_url = analysis['url']
            elif ocr_urls:
                target_url = ocr_urls[0]
            
            if target_url:
                print(f"Fetching webpage: {target_url}")
                webpage_data = self.summarizer.fetch_webpage_content(target_url)
        
        # Step 4: Store analysis data for button callbacks with thread safety
        with self.summarizer.callback_lock:
            self.summarizer.pending_analyses[analysis_id] = {
                'image_path': actual_filepath,
                'analysis': analysis,
                'webpage_data': webpage_data,
                'target_url': target_url,
                'timestamp': current_time.isoformat(),
                'brief_summary': brief_summary
            }
            print(f"Stored analysis data with ID: {analysis_id}")
            print(f"Total stored analyses: {len(self.summarizer.pending_analyses)}")
        
        # Step 5: Send initial message with buttons (including time info)
        if not brief_summary.startswith("Error"):
            telegram_sent = self.summarizer.send_telegram_photo_with_buttons(
                actual_filepath, 
                brief_summary, 
                analysis_id,
                has_webpage=(webpage_data and webpage_data['success']),
                current_time=current_time
            )
            
            if not telegram_sent:
                print("Telegram failed, summary available locally")
        else:
            print(f"Error: {brief_summary}")
        
        # Step 6: Update last screenshot time after successful processing
        self.summarizer.last_screenshot_time = current_time
        print(f"Updated last screenshot time to: {current_time.strftime('%H:%M:%S')}")
        
        # Step 7: Save summary locally
        summary_path = self.summarizer.save_summary(actual_filepath, brief_summary, webpage_data)
        print(f"Summary saved to: {os.path.basename(summary_path)}")
        print(f"Brief summary: {brief_summary[:100]}...\n")

def load_env_file():
    """Load environment variables from .env file if it exists"""
    env_file = '.env'
    if os.path.exists(env_file):
        print(f"Loading environment from {env_file}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

def main():
    print("Enhanced Screenshot Summarizer with arXiv Research Integration")
    print("=" * 65)
    
    load_env_file()
    
    API_KEY = os.getenv('ANTHROPIC_API_KEY')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    
    if not API_KEY:
        API_KEY = input("Enter your Anthropic API key: ").strip()
        if not API_KEY:
            print("Anthropic API key is required!")
            return
    else:
        print("Anthropic API key loaded from environment")
    
    if not TELEGRAM_BOT_TOKEN:
        TELEGRAM_BOT_TOKEN = input("Enter your Telegram Bot Token: ").strip() or None
    else:
        print("Telegram Bot Token loaded from environment")
        
    if not TELEGRAM_CHAT_ID:
        TELEGRAM_CHAT_ID = input("Enter your Telegram Chat ID: ").strip() or None
    else:
        print("Telegram Chat ID loaded from environment")
    
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("Telegram configured - interactive research summaries will be sent")
        test_summarizer = EnhancedScreenshotSummarizer(API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        if test_summarizer.send_telegram_message("*Enhanced Screenshot Summarizer with arXiv Research*\n\nNow providing brief summaries with arXiv research integration and time tracking!"):
            print("Telegram test message sent successfully")
        else:
            print("Telegram test failed - please check credentials")
    else:
        print("Telegram not configured - summaries will be saved locally only")
    
    screenshots_dir = os.path.expanduser('~/Desktop')
    if not os.path.exists(screenshots_dir):
        screenshots_dir = os.path.expanduser('~/')
        print(f"Desktop not found, monitoring home directory: {screenshots_dir}")
    
    print(f"\nMonitoring: {screenshots_dir}")
    print("NEW: Brief summaries with arXiv research button and time tracking!")
    print("Take a screenshot to test the enhanced features!")
    print("Press Ctrl+C to stop.\n")
    
    summarizer = EnhancedScreenshotSummarizer(API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, screenshots_dir)
    
    observer = Observer()
    observer.schedule(
        ScreenshotHandler(summarizer), 
        screenshots_dir, 
        recursive=False
    )
    
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\nStopping enhanced screenshot monitor...")
        
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            summarizer.send_telegram_message("*Enhanced Screenshot Summarizer Stopped*\n\nNo longer monitoring for screenshots.")
        
        print("Goodbye!")
    
    observer.join()

if __name__ == "__main__":
    main()