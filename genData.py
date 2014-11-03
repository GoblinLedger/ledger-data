import wowapi
import wowapi.utility
from wowapi import APIError
import json
import os
import time

class LedgerRealmAHStats(object):

    def __init__(self, data_directory, slug):

        self.slug = slug
        self.stats_filename = slug + '.json'
        self.auctions_filename = slug + '-auctions.json'
        self.player_filename = slug + '-players.json'

        self.data_directory = data_directory

        self.auctions = []

        # Realm wide stats
        self.buyout_total = 0
        self.auction_count = 0
        self.items = 0

        # (player, realm) => {stats} mapping
        self.players = {}

        # Caculated values

    def _player_auction(self, auction_entry):
        """Takes a auction entry and caculates stats for the player."""

        player = auction_entry['owner']
        player_realm = auction_entry['ownerRealm']

        player_stats = None
        if (player, player_realm) in self.players:
            player_stats = self.players[(player, player_realm)]
        else:
            template = {
                'stats': {
                    'auction_count': 0,
                    'buyout_total': 0,
                    'items': 0
                },
                'auctions': []
            }
            player_stats = template
            self.players[(player, player_realm)] = player_stats

        player_stats['stats']['auction_count'] = player_stats['stats']['auction_count'] + 1
        player_stats['stats']['buyout_total'] = player_stats['stats']['buyout_total'] + auction_entry['buyout']
        player_stats['stats']['items'] = player_stats['stats']['items'] + auction_entry['quantity']

        player_stats['auctions'].append(auction_entry)

    def add(self, auction_entry):

        self.auctions.append(auction_entry)

        self._player_auction(auction_entry)

        # Realm wide stats
        self.buyout_total = auction_entry['buyout'] + self.buyout_total
        self.auction_count = self.auction_count + 1
        self.items = self.items + auction_entry['quantity']

    def _caculate(self):
        pass

    def write(self):

        # Make sure to update caculations before saving the realm files
        self._caculate()


        # Save the players file
        players = {'players': []}
        for player in self.players:
            entry = dict()
            entry['player'] = player[0]
            entry['realm'] = player[1]
            entry['stats'] = self.players[player]['stats']
            entry['auctions'] = self.players[player]['auctions']

            players['players'].append(entry)

        f = open(os.path.join(self.data_directory, self.player_filename), 'wb')
        json.dump(players, f,indent=4, separators=(',', ': '))
        f.close()


        # Save the overall realm stats
        realm = dict()

        realm['buyout_total'] = self.buyout_total
        realm['auction_count'] = self.auction_count
        realm['items'] = self.items

        f = open(os.path.join(self.data_directory, self.stats_filename), 'wb')
        json.dump(realm, f,indent=4, separators=(',', ': '))
        f.close()

        # Save the auciton file
        f = open(os.path.join(self.data_directory, self.auctions_filename), 'wb')
        json.dump({'auctions': self.auctions}, f)
        f.close()

def auctions(realmStatus):
    """ Auction generator. Given a realm auction house status message, returns all auctions. """
    auction_data = wowapi.utility.retrieve_auctions(realmStatus)['files'][0]['data']['auctions']

    for auction in auction_data['auctions']:
        yield auction

def main():
    required_environment = [
        'LEDGER_DATA',
        'LEDGER_API_KEY'
    ]

    if not all(x in os.environ for x in required_environment):
        print("Environment Variables Missing")
        exit(1)

    # Verify the data directory exits
    data_directory = os.path.abspath(os.environ['LEDGER_DATA'])
    if not os.path.isdir(data_directory):
        print("Unknown data path. Please ensure LEDGER_DATA is a valid directory.")
        exit(1)

    #Set the api key and create the api object
    api_key = os.environ['LEDGER_API_KEY']
    api = wowapi.API(api_key)

    # Since connected realms share an auction house,
    # get the list of auciton houses and create a slug => realm name map
    realm_status = api.realm_status()
    slug_map = dict()
    valid_slugs = [realm['slug'] for realm in realm_status['realms']]
    auction_houses = set()
    for realm in realm_status['realms']:
        slug_map[realm['slug']] = realm['name']
        auction_houses.add(frozenset([x for x in realm['connected_realms'] if x in valid_slugs]))


    #Realms Dictionary. This serves as the entry point to the data
    realms = {'realms': []}

    # Loop through the auction houses, picking a random realm to get the snapshot
    for auction_house in auction_houses:
        random_realm = next(iter(auction_house))

        ah_status = api.auction_status(random_realm)

        # Get the auction status
        tries = 0
        while 'files' not in ah_status or tries < 4:
            tries = tries + 1
            ah_status = api.auction_status(random_realm)

        # Create the realm entry for all realms connected to random_realm
        for connected_realm in auction_house:
            realm = dict()
            realm['name'] = slug_map[connected_realm]
            realm['slug'] = connected_realm
            realm['lastModified'] = ah_status['files'][0]['lastModified']
            realm['stats'] = random_realm + '.json'
            realm['auction_file'] = random_realm + '-auctions.json'

            realms['realms'].append(realm)

        # Create the stats information for this realm file
        stats = LedgerRealmAHStats(data_directory, random_realm)
        for auction in auctions(ah_status):
            stats.add(auction)

        # Save the stats files
        stats.write()

        # Sleep timer to avoid going over our calls per second
        time.sleep(1)


    # Output the main realm file
    realm_file = os.path.join(data_directory,'realms.json')
    f = open(realm_file, 'wb')
    json.dump(realms, f, indent=4, separators=(',', ': '))
    f.close()



if __name__ == "__main__":
    main()
