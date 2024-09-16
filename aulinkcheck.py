
import requests
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading

# Setup logging
logging.basicConfig(level=logging.DEBUG,  # Set to DEBUG for detailed output
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler('link_check_log.txt'),
                        logging.StreamHandler()  # Output to console
                    ])

# Create a session object to reuse connections
session = requests.Session()

# Thread-safe set to store checked links
checked_links = set()
checked_links_lock = threading.Lock()

# Dictionary to keep track of the navigation path to each URL
url_paths = {}

def get_links(url):
    """Get all links from the given URL."""
    try:
        response = session.get(url, timeout=5)
        if response.status_code != 200:
            logging.warning(f"Non-200 status code {response.status_code} for URL: {url}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        links = set()
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(url, href)
            if "kmart.com.au" in full_url and not ("jobs.kmart.com.au" in full_url or "kmartgroupcareers" in full_url):
                links.add(full_url)
        return links
    except Exception as e:
        logging.error(f"Error fetching links from {url}: {e}")
        return []

def check_link(url, retries=3):
    """Check if the link returns a 200 status code with retry."""
    for _ in range(retries):
        try:
            response = session.get(url, timeout=10)
            status = response.status_code
            logging.info(f"{url} - Status: {status}")
            if status == 200:
                return status
            else:
                with open('verified_failed_links.txt', 'a') as f:
                    path = url_paths.get(url, 'Unknown path')
                    f.write(f"{url} (Path: {path})\n")
                return status
        except requests.RequestException as e:
            logging.error(f"Error checking {url}: {e}")
            time.sleep(1)  # Wait before retrying
    with open('verified_failed_links.txt', 'a') as f:
        path = url_paths.get(url, 'Unknown path')
        f.write(f"Error checking {url} (Path: {path}): {e}\n")
    return None

def worker(url, path):
    """Worker function to check links and fetch new links."""
    with checked_links_lock:
        if url not in checked_links:
            checked_links.add(url)
            url_paths[url] = path
            logging.info(f"Checking link: {url} (Path: {path})")
            status = check_link(url)
            if status == 200:
                new_links = get_links(url)
                return new_links, path
    return [], path

def recheck_links():
    """Recheck the links in verified_failed_links.txt three times."""
    for _ in range(3):
        with open('verified_failed_links.txt', 'r') as f:
            links = f.readlines()
        
        temp_invalid_links = []
        for line in links:
            url = line.split(' ')[0]
            status = check_link(url)
            if status != 200:
                temp_invalid_links.append(line)
            else:
                logging.info(f"Link rechecked and valid: {url}")
        
        with open('verified_failed_links.txt', 'w') as f:
            f.writelines(temp_invalid_links)

def main(start_url, num_threads=10):
    """Main function to start link checking."""
    start_time = time.time()
    
    # Initialize the list of futures
    futures_to_urls = {}

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        # Submit the initial URL for processing
        future = executor.submit(worker, start_url, start_url)
        futures_to_urls[future] = start_url

        while futures_to_urls:
            for future in as_completed(futures_to_urls):
                try:
                    new_links, path = future.result()
                    for link in new_links:
                        if link not in checked_links:
                            new_path = path + " -> " + link
                            new_future = executor.submit(worker, link, new_path)
                            futures_to_urls[new_future] = link
                except Exception as e:
                    logging.error(f"Error processing future: {e}")
                del futures_to_urls[future]

    logging.info(f"All threads have been stopped. Total runtime: {time.time() - start_time} seconds")

    recheck_links()



if __name__ == "__main__":
    start_url = 'https://www.kmart.com.au/'
    main(start_url)
   
