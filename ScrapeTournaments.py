from time import sleep
import random
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException
from selenium.webdriver.common.by import By
import googlemaps
import csv
import os

gmaps = googlemaps.Client(os.getenv('GMAP_API_KEY'))
geocodes = {}
info_window_dict = {}
tournaments = []
browser = webdriver.Safari()


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
        # Initialize all by indicating they are not to be deleted
        t['tbd'] = False

    for t in tournaments:
        iw = '<p>' + t['name'] + "<br />" + t['date'] + "<br />" + t['tournament_href'] + \
             '<br />' + t['tournament_state'] + '</p>'
        # Now, check to see if we already processed a tournament with this address
        if t['formatted_address'] in info_window_dict:
            # First, remove the previous tournament so we don't get two pins
            for ot in tournaments:
                if ot['formatted_address'] == t['formatted_address']:
                    # If it's already been marked for deletion, find the next one
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
                   'info_window', 'tournament_state', 'tournament_href', 'tbd']
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
                'tbd': False
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
                'tbd': False
            }
            tournaments.append(tournament_dict)
        else:
            print('Geocode failed with location = ', location)
    return


def get_tournaments():
    # Get cached geocoding results
    read_geocodes()

    # The following block of code is useful during debugging. After an initial scrape, the list of tournaments can
    # be written out to a file that is read in during subsequent debugging sessions, eliminating the need for
    # time consuming scrapes

    # csv_file = "Tournaments1.csv"
    # csv_columns = ['name', 'date', 'unformatted_address', 'formatted_address', 'lat', 'lng', 'web_source',
    #                'info_window', 'tournament_state', 'tbd']
    # tournaments = []
    #
    # # If the file exists, read in the contents and return them
    # if exists(csv_file):
    #     input_file = csv.DictReader(open(csv_file))
    #     # Convert strings to floats for lat/lng
    #     for row in input_file:
    #         row['lat'] = float(row['lat'])
    #         row['lng'] = float(row['lng'])
    #         tournaments.append(row)
    #     create_info_window(tournaments)  # Create the info_window text
    #     write_tournaments(tournaments, 'Tournaments.csv')
    #     return tournaments
    # else:
    #     print(csv_file, ' not found')

    # This routine scrapes PickleballBrackets.com and PickleballBrackets.com creates a list of tournaments
    # Each tournament is a dictionary
    # The tournaments are written to a csv file

    scrape_pb_tournaments()
    scrape_pb_brackets()

    # The following line of code is useful during debugging and should be uncommented in conjunction with the block of
    # code at the top of this routine
    # write_tournaments('Tournaments1.csv')

    create_info_window()  # Create the info_window text
    write_tournaments('Tournaments.csv')

    return
