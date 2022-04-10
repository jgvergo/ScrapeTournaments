from time import sleep
import random
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException
from selenium.webdriver.common.by import By
import googlemaps
import csv


gmaps = googlemaps.Client(key='AIzaSyD_LySOPjfrx0Bl_2wxyxGN6HBJ2p4Hqqw')
geocodes = {}


def rand_sleep(avg, plus_or_minus):
    sleep4 = avg + 2*plus_or_minus*random.uniform(0, 1) - plus_or_minus
    sleep(sleep4)


# Create the info_window text
def create_info_window(tournaments):
    for t in tournaments:
        iw = '<p>' + t['name'] + "<br />" + t['date'] + "<br />" + \
                           '<a href=https://www.' + \
                            t['web_source'] + '.com ' + \
                           'target=' + \
                            '"' + '_blank' + '">' + \
                            t['web_source'] + '</a>' + \
                            '<br />' + t['tournament_state'] + \
                            '</p>'
        t['info_window'] = iw


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
                                       {'lat': geocodes[location]['lat'],
                                       'lng': geocodes[location]['lng']}
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
                row = { 'unformatted_address': location,
                      'formatted_address': geodata[0]['formatted_address'],
                      'lat': geodata[0]['geometry']['location']['lat'],
                      'lng': geodata[0]['geometry']['location']['lng']}
                writer.writerow(row)
                csvfile.close()
        except IOError:
            print("I/O error")
    return geodata


def get_tournaments():
    # Get cached geocoding results
    read_geocodes()

    # This routine scrapes PickleballBrackets.com and PickleballBrackets.com creates a list of tournaments
    # Each tournament is a dictionary
    # The tournaments are written to a csv file
    csv_file = "Tournaments.csv"
    csv_columns = ['name', 'date', 'unformatted_address', 'formatted_address', 'lat', 'lng', 'web_source',
                   'info_window', 'tournament_state']
    tournaments = []

    # Scrape PickleballTournaments.com
    # Do the actual web scraping using Selenium and BeautifulSoup
    browser = webdriver.Safari()
    browser.get('https://www.pickleballtournaments.com')
    rand_sleep(7, 2)

    try:
        # Navigate to the "Future Tournaments" page. NB: Need to use browser.execute_script b/c the web element
        # is hidden in a dropdown and the .click() method returns a ElementNotInteractableException
        element = browser.find_element(By.LINK_TEXT, 'Future Tournaments')
        browser.execute_script("arguments[0].click();", element)
    except ElementNotInteractableException:
        print('Unexpected exception')
    except NoSuchElementException:
        print('Unexpected exception')
    rand_sleep(7, 2)

    # At this point, the web page should have all the future tournaments listed
    soup = BeautifulSoup(browser.page_source, 'lxml')

    tl = soup.find("div", class_="tab-pane active tourneylist")
    for row in tl.find_all("div", class_="row"):
        name = row.h3.a.text
        location = row.p.text
        # Sometimes the location is not provided in which case print a message and skip it
        if location == ',' or location == '':
            ostr = name + 'has no location' + location
            print(ostr)
            continue
        tl_date = tl.find("p", class_="tourney-date")
        date = tl_date.text.strip()  # strip removes \nl

        # Get lat, lng, formatted address from cached geocodes or from Google geocode
        geodata = my_geocode(location)

        if row.find("p", class_="closed") is not None:
            tournament_state = 'Registration is closed'
        if row.find("p", class_="soon-date") is not None:
            soon_date = row.find("p", class_="soon-date").text
            tournament_state = 'Registration will open on ' + soon_date
        if row.find("p", class_="open") is not None:
            reg_link = row.find("p", class_="open").find("a").text
            tournament_state = 'Registration is open'

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
                'tournament_state': tournament_state
            }
            tournaments.append(tournament_dict)
        else:
            print('Geocode failed with location = ', location)

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

    for brb in soup.find_all("div", class_="browse-row-box"):
        date = brb.find("div", class_="browse-date").text
        name = brb.find("div", class_="browse-heading").text

        # get_text(separator=" ").strip() replaces <br> with " "
        location = brb.find("div", class_="browse-location").get_text(separator=" ").strip()

        # Sometimes the location is not provided in which case print a message and skip it
        if location == ',' or location == '':
            ostr = name + 'has no location' + location
            print(ostr)
            continue

        # Tournament state = "Completed", etc.
        tournament_state = brb.find("span", class_="state").get_text()
        # Get lat, lng, formatted address from Google geocode
        geodata = my_geocode(location)

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
                'tournament_state': tournament_state
            }
            tournaments.append(tournament_dict)
        else:
            print('Geocode failed with location = ', location)

    create_info_window(tournaments)  # Create the info_window text

    # Now write the csv file so we don't need to do all that work every time
    try:
        with open(csv_file, 'w') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            writer.writerows(tournaments)
    except IOError:
        print("I/O error")

    return
