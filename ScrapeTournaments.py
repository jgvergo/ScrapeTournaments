from time import sleep
import random
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException
from selenium.webdriver.common.by import By
import googlemaps
import csv
import os
from os.path import exists
from datetime import datetime, timedelta

gmaps = googlemaps.Client(os.getenv('GMAP_API_KEY'))
geocodes = {}
info_window_dict = {}
tournaments = []
browser = webdriver.Safari()


# Read in the old tournaments file
def read_tournament_file(csv_file):
    # The following block of code is useful during debugging. After an initial scrape, the list of tournaments can
    # be written out to a file that is read in during subsequent debugging sessions, eliminating the need for
    # time consuming scrapes

    old_tournaments = []

    # If the file exists, read in the contents and return them
    if exists(csv_file):
        input_file = csv.DictReader(open(csv_file))
        # Convert strings to floats for lat/lng
        # Convert dates
        for row in input_file:
            row['lat'] = float(row['lat'])
            row['lng'] = float(row['lng'])
            row['original_scrape_date'] = datetime.strptime(row['original_scrape_date'], '%m/%d/%y')
            old_tournaments.append(row)
        return old_tournaments
    else:
        raise RuntimeError("Could not find " + csv_file)


# This function returns two filenames, one associated with "today" (the date when ScrapeTournaments is run
# and one associated with the most recent run of ScrapeTournaments
def get_tournament_files():
    currentfilename =  datetime.today().strftime('%m-%d-%y') + "Tournaments.csv"
    for x in range(10):
        pastday = datetime.today() - timedelta(x)
        pastdate = datetime.strftime(pastday, '%m-%d-%y')
        pastfilename = pastdate+"Tournaments.csv"
        if exists(pastfilename):
            return pastfilename, currentfilename

    raise RuntimeError("Could not find a recently stored MM-DD-YYTournaments.csv file")


def handle_known_address_exceptions(name):
    # "Manually" handle known exceptions where no location was provided in the "normal" manner but can be
    # found elsewhere on the site
    if name == 'Naples Pickleball Fun Festival 50+ Round Robin Tournament':
        print("Handled address exception: ", name)
        return 'East Naples Community Park, Naples, FL, United States'

    if name == '2022 Fall Classic @  Gilbert Regional by PIG - a USSP Circuit event':
        print("Handled address exception: ", name)
        return 'Gilbert Regional Park 3005 E Queen Creek Rd Gilbert Arizona 85298 United States'

    if name == '2022 Winter Classic @  Gilbert Regional by PIG - a USSP Circuit event':
        print("Handled address exception: ", name)
        return 'Gilbert Regional Park 3005 E Queen Creek Rd Gilbert Arizona 85298 United States'

    return ""


def rand_sleep(avg, plus_or_minus):
    sleep4 = avg + 2 * plus_or_minus * random.uniform(0, 1) - plus_or_minus
    sleep(sleep4)


# Create the info_window text
def create_info_window():
    for t in tournaments:
        # Initialize all by indicating they are not to be deleted ("tbd")
        t['tbd'] = False

    for t in tournaments:
        # Create the content for the info window
        iw = '<p>' + t['name'] + "<br />" + t['date'] + "<br />" + t['tournament_href'] + \
             '<br />' + t['tournament_state'] + '</p>'

        # Now, check to see if we already processed a tournament with this address
        if t['formatted_address'] in info_window_dict:
            # First, remove the previous tournament so we don't get two pins
            for ot in tournaments:
                if ot['formatted_address'] == t['formatted_address']:
                    # If it's already been marked for deletion, find the next one.
                    if ot['tbd']:
                        continue
                    else:
                        # Mark it for deletion
                        ot['tbd'] = True
                        break
            # Next, create the entry with all the info
            t['info_window'] = iw + info_window_dict[t['formatted_address']]
            info_window_dict[t['formatted_address']] = t['info_window']
        else:
            # Simply add the iw content to the tournament
            t['info_window'] = iw
            # ...and add it to the dictionary in case there is another tournament with the same address
            info_window_dict[t['formatted_address']] = iw

    # Now go through and remove all the tournaments that were marked for deletion
    for t in reversed(tournaments):
        if t['tbd']:
            tournaments.remove(t)
    return


# Reads in all of the geocode results from past searches.
def read_geocodes():
    reader = csv.DictReader(open('Geocode_cache.csv'))
    for row in reader:
        key = row.pop('unformatted_address')
        if key in geocodes:
            # implement your duplicate row handling here
            pass
        geocodes[key] = row
    return


# Attempts to find a geocode from the cache
# If it can't find it: 1) call google maps geocode to get the info 2) cache the info for the future
def my_geocode(location):
    try:
        geodata = []
        geo = {'formatted_address': geocodes[location]['formatted_address'],
               'geometry': {'location':
                                {'lat': geocodes[location]['lat'], 'lng': geocodes[location]['lng']}
                            }
               }

        geodata.append(geo)
    except KeyError:
        print('geocoding location = ', location)
        geodata = gmaps.geocode(location)

        # Save the new geocode data in the cache
        try:
            with open('Geocode_cache.csv', 'a+', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=['unformatted_address', 'formatted_address', 'lat', 'lng'])
                row = {'unformatted_address': location,
                       'formatted_address': geodata[0]['formatted_address'],
                       'lat': geodata[0]['geometry']['location']['lat'],
                       'lng': geodata[0]['geometry']['location']['lng']}
                writer.writerow(row)
                csvfile.close()
        except IOError:
            print("I/O error")
    return geodata


def write_tournaments(csv_file):
    csv_columns = ['name', 'date', 'unformatted_address', 'formatted_address', 'lat', 'lng', 'web_source',
                   'info_window', 'tournament_state', 'tournament_href', 'tbd', 'original_scrape_date',
                   'days_since_scrape']
    # Now write the csv file so we don't need to do all that work every time
    try:
        with open(csv_file, 'w') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            writer.writerows(tournaments)
    except IOError:
        print("I/O error")
    return


def scrape_pb_tournaments():
    # Scrape PickleballTournaments.com
    # Do the actual web scraping using Selenium and BeautifulSoup
    browser.get('https://www.pickleballtournaments.com')
    rand_sleep(3, 2)

    try:
        # Navigate to the "Future Tournaments" page. NB: Need to use browser.execute_script b/c the web element
        # is hidden in a dropdown and the .click() method returns a ElementNotInteractableException
        element = browser.find_element(By.LINK_TEXT, 'Future Tournaments')
        browser.execute_script("arguments[0].click();", element)
    except ElementNotInteractableException:
        print('Unexpected exception')
    except NoSuchElementException:
        print('Unexpected exception')
    rand_sleep(3, 2)

    # At this point, the web page should have all the future tournaments listed
    soup = BeautifulSoup(browser.page_source, 'lxml')

    tl = soup.find("div", class_="tab-pane active tourneylist")
    for row in tl.find_all("div", class_="row"):
        name = row.h3.a.text
        location = row.p.text
        # Sometimes the location is not provided in which case print a message and skip it
        if location == ',' or location == '':
            location = handle_known_address_exceptions(name)
            if location == "":
                ostr = name + ' has no location. ADD TO EXCEPTION LIST'
                print(ostr)
                continue
        tl_date = row.find("p", class_="tourney-date")
        date = tl_date.text.strip()  # strip removes \nl

        # Get lat, lng, formatted address from cached geocodes or from Google geocode
        geodata = my_geocode(location)

        if row.find("p", class_="closed") is not None:
            tournament_state = 'Registration is closed'
        elif row.find("p", class_="soon-date") is not None:
            soon_date = row.find("p", class_="soon-date").text
            tournament_state = 'Registration ' + soon_date
        elif row.find("p", class_="open") is not None:
            tournament_state = 'Registration is open'
        elif row.find("p", class_="adonly") is not None:
            tournament_state = 'Tournament Advertisement Only'
        details_button = row.find('p', class_='detailsbutton')
        href = details_button.find('a')['href']
        tournament_url = 'https://www.pickleballtournaments.com/' + href

        tournament_href = '<a href="' + tournament_url + '" target="_blank">' + 'Tournament Details' + '</a>'
        # https: // www.pickleballtournaments.com / tournamentinfo.pl?tid = 5308
        if len(geodata) > 0:
            tournament_dict = {
                'name': name,
                'date': date,
                'unformatted_address': location,
                'formatted_address': geodata[0]["formatted_address"],
                'lat': geodata[0]["geometry"]["location"]["lat"],
                'lng': geodata[0]["geometry"]["location"]["lng"],
                'web_source': 'PickleballTournaments',
                'info_window': '',
                'tournament_state': tournament_state,
                'tournament_href': tournament_href,
                'tbd': False,
                'original_scrape_date': datetime.today()
            }
            tournaments.append(tournament_dict)
        else:
            print('Geocode failed with location = ', location)
    return


def scrape_pb_brackets():
    browser.get('https://pickleballbrackets.com')

    # Keep clicking the "See more" button until we don't find a "btnMoreResults" button
    # (i.e. go through all the pages of tournaments)
    while True:
        # Give the page time to load whether it's the initial load or the result of clicking the btnMoreResults button
        rand_sleep(10, 2)

        # Now try finding and clicking the next button in order to bring up all tournaments
        try:
            element = browser.find_element(By.ID, 'btnMoreResults')
            style = element.get_attribute('style')
            if style == 'display: none;':
                break
            browser.execute_script("arguments[0].click();", element)
        except ElementNotInteractableException:
            break
        except NoSuchElementException:
            break

    # At this point, the web page should have all the tournaments listed
    soup = BeautifulSoup(browser.page_source, 'lxml')

    # browse_row refers to class browse-row-box, the container div for a tournament in PickleballBrackets.com
    for browse_row in soup.find_all("div", class_="browse-row"):
        date = browse_row.find("div", class_="browse-date").text
        name = browse_row.find("div", class_="browse-heading").text

        # get_text(separator=" ").strip() replaces <br> with " "
        location = browse_row.find("div", class_="browse-location").get_text(separator=" ").strip()

        # Sometimes the location is not provided in which case print a message and skip it
        if location == ',' or location == '':
            location = handle_known_address_exceptions(name)
            if location == "":
                ostr = name + ' has no location. ADD TO EXCEPTION LIST'
                print(ostr)
                continue

        # Tournament state = "Completed", etc.
        tournament_state = browse_row.find("span", class_="state").get_text()
        # Get lat, lng, formatted address from Google geocode
        geodata = my_geocode(location)

        # Now get the tournament id. This is used to create a link to the tournament page
        foo = browse_row.find('div', class_='browse-row-inner flex')
        onclick = foo.get('onclick')
        tournament_id = onclick.split("'")[1]
        tournament_href = '<a href="https://www.PickleballBrackets.com/ptd.aspx?eid=' + tournament_id + '" ' + \
                          'target="_blank">' + 'Tournament Details' + '</a>'

        if len(geodata) > 0:
            tournament_dict = {
                'name': name,
                'date': date,
                'unformatted_address': location,
                'formatted_address': geodata[0]["formatted_address"],
                'lat': geodata[0]["geometry"]["location"]["lat"],
                'lng': geodata[0]["geometry"]["location"]["lng"],
                'web_source': 'PickleballBrackets',
                'info_window': '',
                'tournament_state': tournament_state,
                'tournament_href': tournament_href,
                'tbd': False,
                'original_scrape_date': datetime.today()
            }
            tournaments.append(tournament_dict)
        else:
            print('Geocode failed with location = ', location)
    return


def get_tournaments():
    # Get cached geocoding results
    read_geocodes()

    # This routine scrapes PickleballBrackets.com and PickleballBrackets.com creates a list of tournaments
    # Each tournament is a dictionary
    # The tournaments are written to a csv file

    # The "core" of the process...scrape sites and build the info_windows that pop up when a user
    # clicks on a pin
    scrape_pb_tournaments()
    scrape_pb_brackets()
    create_info_window()  # Create the info_window text

    # Now we handle "recent additions" to the map
    # The old tournament file has a column called "original_scrape_date"
    # Go through the new set of tournaments, see if it's in the old file and if it is, copy its
    # original_scrape_date.
    # Note: this has the effect of 1) Dropping tournaments that are no longer on the scraped sites and
    # 2) Always have a record of when a tournament was first scraped.
    # NB: The first time this was implemented was on 7/30/22. The "old" file was manually filled with
    # an original_scrape_date of 2022-07-28.

    pastfilename, currentfilename = get_tournament_files()
    old_tournaments = read_tournament_file(pastfilename)
    for t in tournaments:
        # Start by assuming it was scraped today
        t['original_scrape_date'] = datetime.today().date()
        t['days_since_scrape'] = 0

        # See if this tournament existed in the most recent tournament file
        for old_t in old_tournaments:
            if t['tournament_href'] not in old_t['info_window']:
                continue
            else:
                # If we find it in the old info_window, then assign the actual scrape date
                t['original_scrape_date'] = old_t['original_scrape_date'].date()
                d0 = datetime.today()
                d1 = old_t['original_scrape_date']
                delta = d0 - d1
                t['days_since_scrape'] = delta.days
                break

    write_tournaments(currentfilename)
    # For convenience, write it a second time to the application directory
    write_tournaments("../PickleballMaps/Tournaments.csv")

    return
