import requests
from bs4 import BeautifulSoup
from datetime import datetime
import sys

BASE_URL = "https://selfservice.broxtowe.gov.uk"
FORM_GUID = "2a9c4d92-ef0c-4e45-960a-35d062c9c2d1"
OBJECT_TEMPLATE_ID = "217"
FORM_KEY = "9D2EF214E144EE796430597FB475C3892C43C528"
INITIAL_SECTION_ID = "748"

class ScraperError(Exception):
    """Base class for scraper errors"""
    pass

class ClientError(ScraperError):
    """Raised when the inputs are invalid"""
    pass

class UpstreamError(ScraperError):
    """Raised when the response back from Broxtowe is invalid"""
    pass

class ServiceUnavailableError(ScraperError):
    """Raised when the service is unavailable"""
    pass

class InvalidResponseError(ScraperError):
    """Raised when the response is invalid"""
    pass

def parse_bin_data(html_content):
    """
    Parses the HTML content to extract bin collection data.

    Args:
        html_content (str): The HTML content to parse

    Returns:
        list: A list of dictionaries containing bin data

    Raises:
        UpstreamError: If no bin collection data is found
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', {'class': 'bartec'})

    if not table:
        raise UpstreamError("No bin collection data found")

    bins = []
    rows = table.find_all('tr')[1:]  # Skip header row

    for row in rows:
        cols = row.find_all('td')
        if len(cols) == 4:
            next_collection_raw = cols[3].text.strip()
            try:
                # Parse the date string (format: "Wednesday, 02 July 2025")
                date_obj = datetime.strptime(next_collection_raw, "%A, %d %B %Y")
                next_collection_iso = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                next_collection_iso = ""

            bin_data = {
                'type': cols[0].text.strip(),
                'next_collection_raw': next_collection_raw,
                'next_collection_iso': next_collection_iso,
            }
            bins.append(bin_data)

    if not bins:
        raise UpstreamError("No bin collection data found")

    return bins

def validate_response(response: requests.Response):
    """Validate the HTTP response and raise appropriate exceptions"""
    if response.status_code == 503:
        raise ServiceUnavailableError("Broxtowe Borough Council website is currently unavailable")
    if response.status_code == 404:
        raise InvalidResponseError(
                "Broxtowe Borough Council requested page was not found"
        )
    if response.status_code >= 500:
        raise ServiceUnavailableError(
                f"Server error: {response.status_code}, {response.text}"
        )

    if response.status_code >= 400:
        raise InvalidResponseError(
                f"Client error: {response.status_code}, {response.text}"
        )

    if not response.ok:
        raise InvalidResponseError(f"Unexpected response: {response.status_code}, {response.text}")

def format_uprn(uprn):
    return f"U{uprn}"

def get_user_agent():
    return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0 BroxtoweBinCollectionScraper/1.0 (+https://github.com/timtjtim/BroxtoweBinCollectionScraper;)"

def get_bin_data(postcode, uprn):
    """
    Returns the bin collection data for a given postcode and UPRN.

    Args:
        postcode (str): The postcode to search for
        uprn (str): The Unique Property Reference Number

    Returns:
        str: The HTML content of the page containing the bin data
    """
    postcode = postcode.lower().replace(" ", "")
    uprn = format_uprn(uprn.upper().lstrip('U'))

    session = requests.Session()

    # Step 1: GET the initial form page to obtain cookies and the verification token
    initial_url = f"{BASE_URL}/renderform?t={OBJECT_TEMPLATE_ID}&k={FORM_KEY}"
    response = session.get(initial_url, headers={
        "user-agent": get_user_agent(),
    })

    validate_response(response)

    # if not response.ok:
    #     raise ServiceUnavailableError(f"Failed to load initial form page: {response.status_code}")

    soup = BeautifulSoup(response.text, 'html.parser')

    # Extract the __RequestVerificationToken
    token_input = soup.find('input', {'name': '__RequestVerificationToken'})
    if not token_input:
        raise UpstreamError("Could not find __RequestVerificationToken in form page")
    verification_token = token_input['value']

    # Step 2: POST to submit the form with the address (postcode search + UPRN selection)
    # This mirrors the AJAX request from sample-fetch.js
    form_data = {
        "__RequestVerificationToken": verification_token,
        "FormGuid": FORM_GUID,
        "ObjectTemplateID": OBJECT_TEMPLATE_ID,
        "Trigger": "submit",
        "CurrentSectionID": INITIAL_SECTION_ID,
        "TriggerCtl": "",
        "FF5683": uprn,
        "FF5683lbltxt": "Address",
        "FF5683-text": postcode,
    }

    headers = {
        "user-agent": get_user_agent(),
        "accept": "text/plain, */*; q=0.01",
        "content-type": "application/x-www-form-urlencoded",
        "x-requested-with": "XMLHttpRequest",
        "referer": initial_url,
    }

    response = session.post(
        f"{BASE_URL}/renderform/Form",
        headers=headers,
        data=form_data,
    )

    if not response.ok:
        raise ServiceUnavailableError(f"Failed to submit form: {response.status_code}")

    # Parse the bin collection data
    bin_data = parse_bin_data(response.text)

    return {
        'bin_collections': bin_data,
    }

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scrape.py <postcode> <uprn>")
        sys.exit(1)

    postcode = sys.argv[1]
    uprn = sys.argv[2]

    result = get_bin_data(postcode, uprn)

    print(result)
