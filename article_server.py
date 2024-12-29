import asyncio
import json
import numpy as np
import os
from datetime import datetime
from pir import (
    SimplePIRParams, gen_params, gen_hint,
    answer as pir_answer
)
from utils import strings_to_matrix

class ArticleServer:
    def __init__(self, host='127.0.0.1', port=8889):  # Note different default port
        self.host = host
        self.port = port
        self.load_data()
    
    def load_data(self):
        """Load and process article contents"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{timestamp}] Loading article contents database...")
        articles = []
        article_dir = 'articles'
        
        # Load metadata to ensure correct article order
        with open('embeddings/metadata.json', 'r') as f:
            metadata = json.load(f)
        
        # Load articles in the same order as embeddings
        for article_info in metadata['articles']:
            with open(article_info['filepath'], 'r', encoding='utf-8') as f:
                articles.append(f.read())
        
        # Convert articles to matrix
        self.articles_db, matrix_size = strings_to_matrix(articles)
        self.articles_params = gen_params(m=matrix_size)
        self.articles_hint = gen_hint(self.articles_params, self.articles_db)
        self.num_articles = len(articles)
        
        print(f"[{timestamp}] Initialized with {len(articles)} articles")
        print(f"[{timestamp}] Articles matrix size: {matrix_size}x{matrix_size}")
    
    async def update_loop(self):
        """Periodically update article data"""
        while True:
            await asyncio.sleep(60)  # Wait for 1 minute
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n[{timestamp}] Reloading article data...")
                self.load_data()
                print(f"[{timestamp}] Article update complete!")
            except Exception as e:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{timestamp}] Error during article update: {e}")
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info('peername')
        print(f"New connection from {addr}")
        
        try:
            # Send setup data
            setup_data = {
                'params': {
                    'n': int(self.articles_params.n),
                    'm': int(self.articles_params.m),
                    'q': int(self.articles_params.q),
                    'p': int(self.articles_params.p),
                    'std_dev': float(self.articles_params.std_dev)
                },
                'hint': self.articles_hint.tolist(),
                'a': self.articles_params.a.tolist(),
                'num_articles': self.num_articles
            }
            
            # Send length-prefixed data
            data = json.dumps(setup_data).encode()
            length = len(data)
            writer.write(f"{length}\n".encode())
            await writer.drain()
            
            writer.write(data)
            await writer.drain()

            while True:
                # Read length-prefixed query
                length = await reader.readline()
                if not length:
                    break
                length = int(length.decode().strip())
                
                # Read query data
                data = await reader.readexactly(length)
                query_data = json.loads(data.decode())
                query = np.array(query_data['query'])
                
                ans = pir_answer(query, self.articles_db, self.articles_params.q)
                
                response = {
                    'answer': ans.tolist()
                }
                
                # Send length-prefixed response
                response_data = json.dumps(response).encode()
                writer.write(f"{len(response_data)}\n".encode())
                await writer.drain()
                
                writer.write(response_data)
                await writer.drain()
                
        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally:
            print(f"Connection closed for {addr}")
            writer.close()
            await writer.wait_closed()
    
    async def start(self):
        server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        
        addr = server.sockets[0].getsockname()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Serving articles on {addr}")
        
        # Start the update loop
        asyncio.create_task(self.update_loop())
        
        async with server:
            await server.serve_forever()

if __name__ == "__main__":
    server = ArticleServer()
    asyncio.run(server.start()) 