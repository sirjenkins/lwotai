'''
LWOTai - A Python implementation of the Single-Player AI for Labyrinth: the War on Terror by GMT Games.
Mike Houser, 2011

Thanks to Dave Horn for implementing the Save and Undo system.

1. A save game is created after every single command whether you want it or not. If someone screws up and closes the window, pc battery dies, crashes, whatever, no problem, load it up again and you will be asked if you want to load the suspended game.

2. Rollback files are created at the beginning of each turn. You can rollback to any previous turn using 'roll' or 'rollback' command. You will be prompted to enter which turn you want to rollback to.

3. An undo file is created after every card played. Player can undo to the last card at any time (two exceptions) by typing 'undo'. Exceptions are when you load from a previously suspended game or after executing a rollback. The undo file is removed at that exact point to prevent player from undoing themselves to some other game in the past!

Release 1.08112011.1

'''

SUSPEND_FILE = "suspend.lwot"
UNDO_FILE = "undo.lwot"
ROLLBACK_FILE = "turn."
MAP_FILE = "map.yml"
SCENARIOS_FILE = "scenarios.yml"

TROOPS_MAX = 15
CELLS_MAX  = 15

import sys
import cmd
import random
import shutil
import re
try:
  import cPickle as pickle
except:
  import pickle
import os.path
import yaml
from enum import IntEnum
from enum import Enum

CONFLICT_STATUS = {
    range(11,16): (9, 'Low Intensity')
  , range(6,11): (8, 'War')
  , range(1,6): (7, 'Overstretched')
}

FUNDING_STATUS = {
    range(7,10): (9, 'Ample')
  , range(4,7): (8, 'Moderate')
  , range(1,4): (7, 'Tight')
}

PRESTIGE_STATUS = {
    range(1,4): ('Low', -1)
  , range(4,7): ('Moderate', 0)
  , range(7,10): ('High', 1)
  , range(10,13): ('Very High', 2)
}

def random_roll():
  return random.randint(1,6)

class Governance(IntEnum):
  ISLAMIST_RULE = 4
  POOR = 3
  FAIR = 2
  GOOD = 1
  TEST = 0

  def __str__(self) : return self.name
  def __format__(self,spec) :
    return format(self.__str__(), spec)

class Alignment(IntEnum):
  NO_ALIGN = -1
  TEST = 0
  ADVERSARY = 1
  NEUTRAL = 2
  ALLY = 3

  def __str__(self) : return self.name
  def __format__(self,spec) :
    return format(self.__str__(), spec)

class Posture(Enum):
  HARD = 'Hard'
  SOFT = 'Soft'
  TEST = '??'
  NO_POS = None
  LOCKED_HARD = 'Hard'

  def __str__(self) :
    return self.value

  def __format__(self,spec) :
    return format(self.__str__(), spec)

COUNTRY_STATS = {'governance': Governance, 'alignment': Alignment}
POSTURE_DIVIDE = 4
GOVERNANCE_DIVIDE = 4

class UnknownCountry(Exception):
  def __init__(self, value):
    self.value = value
  def __str__(self):
    return repr(self.value)

class Country:
  app = None
  name = ""
  culture = ""
  posture = Posture.TEST
  alignment = Alignment.TEST
  governance = Governance.TEST
  schengen = False
  recruit_req = 0
  troops_stationed = 0
  active_cells = 0
  sleeper_cells = 0
  oil = False
  resources = 0
  links = []
  markers = []
  schengenLink = False
  aid = 0
  besiged = 0
  regime_change = 0
  cadre = 0
  plots = 0

  def __init__(self, theApp, country_name, stats):
    self.app = theApp

    self.name = country_name
    self.culture = stats['culture']
    self.posture = Posture[stats['posture']]
    self.alignment = Alignment[stats['alignment']]
    self.governance = Governance[stats['governance']]
    self.schengen = stats['schengen']
    self.recruit_req = stats['recruit_req']
    self.resources = stats['resources']
    self.oil = stats['oil']

    self.troops_stationed = 0
    self.active_cells = 0
    self.sleeper_cells = 0
    self.aid = 0
    self.besieged = 0
    self.regime_change = 0
    self.cadre = 0
    self.plots = 0
    self.links = []
    self.adjacent_countries = []
    self.markers = []
    self.schengenLink = False

  def get_stats(self) :
    return dict(
      c = self
      , name = self.name
      , culture = self.culture
      , posture = self.posture
      , alignment = self.alignment
      , governance = self.governance
      , resources = self.resources
      , troops_stationed = self.troops_stationed
      , active_cells = self.active_cells
      , sleeper_cells = self.sleeper_cells
      , aid = self.aid
      , besieged = self.besieged
      , regime_change = self.regime_change
      , cadre = self.cadre
      , plots = self.plots
    )

  # Culture Queries
  def non_muslim_Q(self):
    return 'Non-Muslim' == self.culture

  def suni_Q(self):
    return 'Suni' == self.culture

  def shia_mix_Q(self):
    return 'Shia-Mix' == self.culture

  def iran_Q(self):
    return 'Iran' == self.culture

  # Governance Queries
  def test_governance_Q(self):
    return Governance.TEST == self.governance
    
  def good_Q(self):
    return Governance.GOOD == self.governance

  def fair_Q(self):
    return Governance.FAIR == self.governance

  def poor_Q(self):
    return Governance.POOR == self.governance

  def islamist_rule_Q(self):
    return Governance.ISLAMIST_RULE == self.governance

  # Alignment Queries
  def ally_Q(self):
    return Alignment.ALLY == self.alignment

  def neutral_Q(self):
    return Alignment.NEUTRAL == self.alignment

  def adversary_Q(self):
    return Alignment.ADVERSARY == self.alignment

  def test_alignment_Q(self) :
    return Alignment.TEST == self.alignment

  # Posture Queries
  def soft_Q(self):
    return Posture.SOFT == self.posture

  def hard_Q(self):
    return Posture.HARD == self.posture or Posture.LOCKED_HARD == self.posture

  def test_posture_Q(self):
    return Posture.TEST == self.posture

  def cadre_Q(self): return self.cadre == 1
  def plot_Q(self): return self.plots > 1

  def remove_cadre(self): self.cadre = 0
  def add_cadre(self): self.cadre = 1

  def aid_Q(self) : return self.aid > 0
  def besieged_Q(self) : return self.besieged > 0
  def regime_change_Q(self) : return self.regime_change > 0

  def totalCells(self, includeSadr = False):
    total = self.active_cells + self.sleeper_cells
    if includeSadr and "Sadr" in self.markers:
      total += 1
    return total

  def numActiveCells(self):
    total = self.active_cells
    if "Sadr" in self.markers:
      total += 1
    return total

  def removeActiveCell(self):
    self.active_cells -= 1
    if self.active_cells < 0:
      if "Sadr" in self.markers:
        self.markers.remove("Sadr")
        self.app.outputToHistory("Sadr removed from %s" % self.name, False)
        return
      else:
        self.active_cells = 0
    self.app.outputToHistory("Active cell Removed to Funding Track", False)
    self.app.cells += 1

  def troops(self):
    troopCount = self.troops_stationed
    if "NATO" in self.markers:
      troopCount += 2
    return troopCount

  def changeTroops(self, delta):
    self.troops_stationed += delta
    if self.troops_stationed < 0:
      if "NATO" in self.markers:
        self.markers.remove("NATO")
        self.app.outputToHistory("NATO removed from %s" % self.name, True)
      self.troops_stationed = 0

  def govStr(self):
    if self.good_Q():
      return "Good"
    elif self.fair_Q():
      return "Fair"
    elif self.poor_Q():
      return "Poor"
    elif self.islamist_rule_Q():
      return "Islamic Rule"

  def typePretty(self, culture):
    if non_muslim_Q():
      return "NM"
    elif suni_Q():
      return "SU"
    elif shia_mix_Q():
      return "SM"
    else:
      return "IR"

class Card:
  number = 0
  name = ""
  type = ""
  ops = 0
  remove = False
  mark = False
  lapsing = False

  def __init__(self, theNumber, theType, theName, theOps, theRemove, theMark, theLapsing):
    self.number = theNumber
    self.name = theName
    self.type = theType
    self.ops = theOps
    self.remove = theRemove
    self.mark = theMark
    self.lapsing = theLapsing

  def playable(self, side, app):
    if self.type == "US" and side == "Jihadist":
      return False
    elif self.type == "Jihadist" and side == "US":
      return False
    elif self.type == "US" and side == "US":
      if self.number == 1: # Backlash
        for country in app.map:
          if (not app.map[country].non_muslim_Q()) and (app.map[country].plots > 0):
            return True
        return False
      elif self.number == 2: # Biometrics
        return True
      elif self.number == 3: # CRT
        return app.map["United States"].soft_Q()
      elif self.number == 2: # Biometrics
        return True
      elif self.number == 4: # Moro Talks
        return True
      elif self.number == 5: # NEST
        return True
      elif self.number == 6 or self.number == 7 : # Sanctions
        return "Patriot Act" in app.markers
      elif self.number == 8 or self.number == 9 or self.number == 10: # Special Forces
        for country in app.map:
          if app.map[country].totalCells(True) > 0:
            for subCountry in app.map:
              if country == subCountry or app.isAdjacent(subCountry, country):
                if app.map[subCountry].troops() > 0:
                  return True
        return False
      elif self.number == 11: # Abbas
        return True
      elif self.number == 12: # Al-Azhar
        return True
      elif self.number == 13: # Anbar Awakening
        return (app.map["Iraq"].troops() > 0) or (app.map["Syria"].troops() > 0)
      elif self.number == 14: # Covert Action
        for country in app.map:
          if app.map[country].alignment == "Adversary":
            return True
        return False
      elif self.number == 15: # Ethiopia Strikes
        return (app.map["Somalia"].islamist_rule_Q()) or (app.map["Sudan"].islamist_rule_Q())
      elif self.number == 16: # Euro-Islam
        return True
      elif self.number == 17: # FSB
        return True
      elif self.number == 18: # Intel Community
        return True
      elif self.number == 19: # Kemalist Republic
        return True
      elif self.number == 20: # King Abdullah
        return True
      elif self.number == 21: # Let's Roll
        allyGoodPlotCountries = 0
        for country in app.map:
          if app.map[country].plots > 0:
            if app.map[country].ally_Q() or app.map[country].good_Q():
              allyGoodPlotCountries += 1
        return allyGoodPlotCountries > 0
      elif self.number == 22: # Mossad and Shin Bet
        targetCells = 0
        targetCells += app.map["Israel"].totalCells()
        targetCells += app.map["Jordan"].totalCells()
        targetCells += app.map["Lebanon"].totalCells()
        return targetCells > 0
      elif self.number == 23 or self.number == 24 or self.number == 25: # Predator
        numMuslimCellCountries = 0
        for country in app.map:
          if app.map[country].totalCells(True) > 0:
            if app.map[country].suni_Q() or app.map[country].shia_mix_Q():
              numMuslimCellCountries += 1
        return numMuslimCellCountries > 0
      elif self.number == 26: # Quartet
        if not "Abbas" in app.markers:
          return False
        if app.troops <= 4:
          return False
        for country in app.map:
          if app.isAdjacent(country, "Israel"):
            if app.map[country].islamist_rule_Q():
              return False
        return True
      elif self.number == 27: # Saddam Captured
        return app.map["Iraq"].troops() > 0
      elif self.number == 28: # Sharia
        return app.numBesieged() > 0
      elif self.number == 29: # Tony Blair
        return True
      elif self.number == 30: # UN Nation Building
        numRC = app.numRegimeChange()
        return (numRC > 0) and ("Vieira de Mello Slain" not in app.markers)
      elif self.number == 31: # Wiretapping
        if "Leak-Wiretapping" in app.markers:
          return False
        for country in ["United States", "United Kingdom", "Canada"]:
          if app.map[country].totalCells() > 0 or app.board.cadre_Q(country) or app.map[country].plots > 0:
            return True
        return False
      elif self.number == 32: # Back Channel
        if app.map["United States"].hard_Q():
          return False
        numAdv = app.numAdversary()
        if numAdv <= 0:
          return False
        app.listAdversaryCountries()
        return app.getYesNoFromUser("Do you have a card with a value that exactly matches an Adversary's Resources? (y/n): ")
      elif self.number == 33: # Benazir Bhutto
        if "Bhutto Shot" in app.markers:
          return False
        if app.map["Pakistan"].islamist_rule_Q():
          return False
        for countryObj in app.map["Pakistan"].links:
          if countryObj.islamist_rule_Q():
            return False
        return True
      elif self.number == 34: # Enhanced Measures
        if "Leak-Enhanced Measures" in app.markers or app.map["United States"].soft_Q():
          return False
        return app.numDisruptable() > 0
      elif self.number == 35: # Hajib
        return app.numIslamicRule() == 0
      elif self.number == 36: # Indo-Pakistani Talks
        if app.map['Pakistan'].good_Q() or app.map['Pakistan'].fair_Q():
          return True
        return False
      elif self.number == 37: # Iraqi WMD
        if app.map["United States"].hard_Q() and app.map["Iraq"].alignment == "Adversary":
          return True
        return False
      elif self.number == 38: # Libyan Deal
        if app.map["Libya"].poor_Q():
          if app.map["Iraq"].ally_Q() or app.map["Syria"].ally_Q():
            return True
        return False
      elif self.number == 39: # Libyan WMD
        if app.map["United States"].hard_Q() and app.map["Libya"].alignment == "Adversary" and "Libyan Deal" not in app.markers:
          return True
        return False
      elif self.number == 40: # Mass Turnout
        return app.numRegimeChange() > 0
      elif self.number == 41: # NATO
        return (app.numRegimeChange() > 0) and (app.board.gwot()['penalty'] >= 0)
      elif self.number == 42: # Pakistani Offensive
        return (app.map["Pakistan"].ally_Q()) and ("FATA" in app.map["Pakistan"].markers)
      elif self.number == 43: # Patriot Act
        return True
      elif self.number == 44: # Renditions
        return (app.map["United States"].hard_Q()) and ("Leak-Renditions" not in app.markers)
      elif self.number == 45: # Safer Now
        if app.numIslamicRule() > 0:
          return False
        for country in app.map:
          if app.map[country].good_Q():
            if app.map[country].totalCells(True) > 0 or app.map[country].plots > 0:
              return False
        return True
      elif self.number == 46: # Sistani
        targetCountries = 0
        for country in app.map:
          if app.map[country].shia_mix_Q():
            if app.map[country].regime_change > 0:
              if (app.map[country].totalCells(True)) > 0:
                targetCountries += 1
        return targetCountries > 0
      elif self.number == 47: # The door of Itjihad was closed
        return True
      else:
        return False
    elif self.type == "Jihadist" and side == "Jihadist":
      if "The door of Itjihad was closed" in app.lapsing:
        return False
      if self.number == 48: # Adam Gadahn
        if app.numCellsAvailable() <= 0:
          return False
        return app.getYesNoFromUser("Is this the 1st card of the Jihadist Action Phase? (y/n): ")
      elif self.number == 49: # Al-Ittihad al-Islami
        return True
      elif self.number == 50: # Ansar al-Islam
        return app.map["Iraq"].governance > 1
      elif self.number == 51: # FREs
        return app.map["Iraq"].troops() > 0
      elif self.number == 52: # IDEs
        for country in app.map:
          if app.map[country].regime_change > 0:
            if (app.map[country].totalCells(True)) > 0:
              return True
        return False
      elif self.number == 53: # Madrassas
        return app.getYesNoFromUser("Is this the 1st card of the Jihadist Action Phase? (y/n): ")
      elif self.number == 54: # Moqtada al-Sadr
        return app.map["Iraq"].troops() > 0
      elif self.number == 55: # Uyghur Jihad
        return True
      elif self.number == 56: # Vieira de Mello Slain
        for country in app.map:
          if app.map[country].regime_change > 0 and app.map[country].totalCells() > 0:
            return True
        return False
      elif self.number == 57: # Abu Sayyaf
        return "Moro Talks" not in app.markers
      elif self.number == 58: # Al-Anbar
        return "Anbar Awakening" not in app.markers
      elif self.number == 59: # Amerithrax
        return True
      elif self.number == 60: # Bhutto Shot
        return app.map["Pakistan"].totalCells() > 0
      elif self.number == 61: # Detainee Release
        if "GTMO" in app.lapsing or "Renditions" in app.markers:
          return False
        return app.getYesNoFromUser("Did the US Disrupt during this or the last Action Phase? (y/n): ")
      elif self.number == 62: # Ex-KGB
        return True
      elif self.number == 63: # Gaza War
        return True
      elif self.number == 64: # Hariri Killed
        return True
      elif self.number == 65: # HEU
        possibles = 0
        if app.map["Russia"].totalCells() > 0 and "CTR" not in app.map["Russia"].markers:
          possibles += 1
        if app.map["Central Asia"].totalCells() > 0 and "CTR" not in app.map["Central Asia"].markers:
          possibles += 1
        return possibles > 0
      elif self.number == 66: # Homegrown
        return True
      elif self.number == 67: # Islamic Jihad Union
        return True
      elif self.number == 68: # Jemaah Islamiya
        return True
      elif self.number == 69: # Kazakh Strain
        return app.map["Central Asia"].totalCells() > 0 and "CTR" not in app.map["Central Asia"].markers
      elif self.number == 70: # Lashkar-e-Tayyiba
        return "Indo-Pakistani Talks" not in app.markers
      elif self.number == 71: # Loose Nuke
        return app.map["Russia"].totalCells() > 0 and "CTR" not in app.map["Russia"].markers
      elif self.number == 72: # Opium
        return app.map["Afghanistan"].totalCells() > 0
      elif self.number == 73: # Pirates
        return app.map["Somalia"].islamist_rule_Q() or app.map["Yemen"].islamist_rule_Q()
      elif self.number == 74: # Schengen Visas
        return True
      elif self.number == 75: # Schroeder & Chirac
        return app.map["United States"].hard_Q()
      elif self.number == 76: # Abu Ghurayb
        targetCountries = 0
        for country in app.map:
          if app.map[country].regime_change > 0:
            if (app.map[country].totalCells(True)) > 0:
              targetCountries += 1
        return targetCountries > 0
      elif self.number == 77: # Al Jazeera
        if app.map["Saudi Arabia"].troops() > 0:
          return True
        for country in app.map:
          if app.isAdjacent("Saudi Arabia", country):
            if app.map[country].troops() > 0:
              return True
        return False
      elif self.number == 78: # Axis of Evil
        return True
      elif self.number == 79: # Clean Operatives
        return True
      elif self.number == 80: # FATA
        return True
      elif self.number == 81: # Foreign Fighters
        return app.numRegimeChange() > 0
      elif self.number == 82: # Jihadist Videos
        return True
      elif self.number == 83: # Kashmir
        return "Indo-Pakistani Talks" not in app.markers
      elif self.number == 84 or self.number == 85: # Leak
        return ("Enhanced Measures" in app.markers) or ("Renditions" in app.markers) or ("Wiretapping" in app.markers)
      elif self.number == 86: # Lebanon War
        return True
      elif self.number == 87 or self.number == 88 or self.number == 89: # Martyrdom Operation
        for country in app.map:
          if app.map[country].governance != 4:
            if app.map[country].totalCells(True) > 0:
              return True
        return False
      elif self.number == 90: # Quagmire
        if app.prestige >= 7:
          return False
        for country in app.map:
          if app.map[country].regime_change > 0:
            if app.map[country].totalCells(True) > 0:
              return True
        return False
      elif self.number == 91: # Regional al-Qaeda
        num = 0
        for country in app.map:
          if app.map[country].suni_Q() or app.map[country].shia_mix_Q():
            if app.map[country].governance == 0:
              num += 1
        return num >= 2
      elif self.number == 92: # Saddam
        if "Saddam Captured" in app.markers:
          return False
        return (app.map["Iraq"].poor_Q()) and (app.map["Iraq"].alignment == "Adversary")
      elif self.number == 93: # Taliban
        return True
      elif self.number == 94: # The door of Itjihad was closed
        return app.getYesNoFromUser("Was a country tested or improved to Fair or Good this or last Action Phase.? (y/n): ")
      elif self.number == 95: # Wahhabism
        return True
    else: # Unassociated Events
      if side == "Jihadist" and "The door of Itjihad was closed" in app.lapsing:
        return False
      if self.number == 96: # Danish Cartoons
        return True
      elif self.number == 97: # Fatwa
        return app.getYesNoFromUser("Do both sides have cards remaining beyond this one? (y/n): ")
      elif self.number == 98: # Gaza Withdrawl
        return True
      elif self.number == 99: # HAMAS Elected
        return True
      elif self.number == 100: # His Ut-Tahrir
        return True
      elif self.number == 101: # Kosovo
        return True
      elif self.number == 102: # Former Soviet Union
        return True
      elif self.number == 103: # Hizballah
        return True
      elif self.number == 104 or self.number == 105: # Iran
        return True
      elif self.number == 106: # Jaysh al-Mahdi
        for country in app.map:
          if app.map[country].shia_mix_Q():
            if app.map[country].troops() > 0 and app.map[country].totalCells() > 0:
              return True
        return False
      elif self.number == 107: # Kurdistan
        return True
      elif self.number == 108: # Musharraf
        if "Benazir Bhutto" in app.markers:
          return False
        return app.map["Pakistan"].totalCells() > 0
      elif self.number == 109: # Tora Bora
        for country in app.map:
          if app.map[country].regime_change > 0:
            if app.map[country].totalCells() >= 2:
              return True
        return False
      elif self.number == 110: # Zarqawi
        return app.map["Iraq"].troops() > 0 or app.map["Syria"].troops() > 0 or app.map["Lebanon"].troops() > 0 or app.map["Jordan"].troops() > 0
      elif self.number == 111: # Zawahiri
        if side == "US":
          if "FATA" in app.map["Pakistan"].markers:
            return False
          if "Al-Anbar" in app.markers:
            return False
          return app.numIslamicRule() == 0
        else:
          return True
      elif self.number == 112: # Bin Ladin
        if side == "US":
          if "FATA" in app.map["Pakistan"].markers:
            return False
          if "Al-Anbar" in app.markers:
            return False
          return app.numIslamicRule() == 0
        else:
          return True
      elif self.number == 113: # Darfur
        return True
      elif self.number == 114: # GTMO
        return True
      elif self.number == 115: # Hambali
        possibles = ["Indonesia/Malaysia"]
        for countryObj in app.map["Indonesia/Malaysia"].links:
          possibles.append(countryObj.name)
        for country in possibles:
          if app.map[country].totalCells(True) > 0:
            if app.map[country].non_muslim_Q():
              if app.map[country].hard_Q():
                return True
            else:
              if app.map[country].ally_Q():
                return True
      elif self.number == 116: # KSM
        if side == "US":
          for country in app.map:
            if app.map[country].plots > 0:
              if app.map[country].non_muslim_Q() or app.map[country].ally_Q():
                return True
          return False
        else:
          return True
      elif self.number == 117 or self.number == 118: # Oil Price Spike
        return True
      elif self.number == 119: # Saleh
        return True
      elif self.number == 120: # US Election
        return True
      return False

  def putsCell(self, app):
    if self.number == 48: # Adam Gadahn
      return True
    elif self.number == 49: # Al-Ittihad al-Islami
      return True
    elif self.number == 50: # Ansar al-Islam
      return True
    elif self.number == 51: # FREs
      return True
    elif self.number == 52: # IDEs
      return False
    elif self.number == 53: # Madrassas
      return True
    elif self.number == 54: # Moqtada al-Sadr
      return False
    elif self.number == 55: # Uyghur Jihad
      return True
    elif self.number == 56: # Vieira de Mello Slain
      return False
    elif self.number == 57: # Abu Sayyaf
      return True
    elif self.number == 58: # Al-Anbar
      return True
    elif self.number == 59: # Amerithrax
      return False
    elif self.number == 60: # Bhutto Shot
      return False
    elif self.number == 61: # Detainee Release
      return True
    elif self.number == 62: # Ex-KGB
      return False
    elif self.number == 63: # Gaza War
      return False
    elif self.number == 64: # Hariri Killed
      return False
    elif self.number == 65: # HEU
      return False
    elif self.number == 66: # Homegrown
      return True
    elif self.number == 67: # Islamic Jihad Union
      return True
    elif self.number == 68: # Jemaah Islamiya
      return True
    elif self.number == 69: # Kazakh Strain
      return False
    elif self.number == 70: # Lashkar-e-Tayyiba
      return True
    elif self.number == 71: # Loose Nuke
      return False
    elif self.number == 72: # Opium
      return True
    elif self.number == 73: # Pirates
      return False
    elif self.number == 74: # Schengen Visas
      return False
    elif self.number == 75: # Schroeder & Chirac
      return False
    elif self.number == 76: # Abu Ghurayb
      return False
    elif self.number == 77: # Al Jazeera
      return False
    elif self.number == 78: # Axis of Evil
      return False
    elif self.number == 79: # Clean Operatives
      return False
    elif self.number == 80: # FATA
      return True
    elif self.number == 81: # Foreign Fighters
      return True
    elif self.number == 82: # Jihadist Videos
      return True
    elif self.number == 83: # Kashmir
      return True
    elif self.number == 84 or self.number == 85: # Leak
      return False
    elif self.number == 86: # Lebanon War
      return True
    elif self.number == 87 or self.number == 88 or self.number == 89: # Martyrdom Operation
      return False
    elif self.number == 90: # Quagmire
      return False
    elif self.number == 91: # Regional al-Qaeda
      return True
    elif self.number == 92: # Saddam
      return False
    elif self.number == 93: # Taliban
      return True
    elif self.number == 94: # The door of Itjihad was closed
      return False
    elif self.number == 95: # Wahhabism
      return False
    elif self.number == 96: # Danish Cartoons
      return False
    elif self.number == 97: # Fatwa
      return False
    elif self.number == 98: # Gaza Withdrawl
      return True
    elif self.number == 99: # HAMAS Elected
      return False
    elif self.number == 100: # His Ut-Tahrir
      return False
    elif self.number == 101: # Kosovo
      return False
    elif self.number == 102: # Former Soviet Union
      return False
    elif self.number == 103: # Hizballah
      return False
    elif self.number == 104 or self.number == 105: # Iran
      return False
    elif self.number == 106: # Jaysh al-Mahdi
      return False
    elif self.number == 107: # Kurdistan
      return False
    elif self.number == 108: # Musharraf
      return False
    elif self.number == 109: # Tora Bora
      return False
    elif self.number == 110: # Zarqawi
      return True
    elif self.number == 111: # Zawahiri
      return False
    elif self.number == 112: # Bin Ladin
      return False
    elif self.number == 113: # Darfur
      return False
    elif self.number == 114: # GTMO
      return False
    elif self.number == 115: # Hambali
      return False
    elif self.number == 116: # KSM
      return False
    elif self.number == 117 or self.number == 118: # Oil Price Spike
      return False
    elif self.number == 119: # Saleh
      return False
    elif self.number == 120: # US Election
      return False
    return False

  def playEvent(self, side, app):
    app.outputToHistory("Card played for Event.", True)
    if self.type == "US" and side == "Jihadist":
      return False
    elif self.type == "Jihadist" and side == "US":
      return False
    elif self.type == "US" and side == "US":
      if self.number == 1: # Backlash
        for country in app.map:
          if (app.map[country].culture != "Non-Muslim") and (app.map[country].plots > 0):
            app.outputToHistory("Plot in Muslim country found. Select the plot. Backlash in play", True)
            app.backlashInPlay = True
            return True
        return False
      elif self.number == 2: # Biometrics
        app.lapsing.append("Biometrics")
        app.outputToHistory("Biometrics in play. This turn, travel to adjacent Good countries must roll to succeed and no non-adjacent travel.", True)
      elif self.number == 3: # CRT
        app.map["Russia"].markers.append("CRT")
        app.outputToHistory("CRT Maker added in Russia", True)
        if (app.map["Central Asia"].ally_Q()) or (app.map["Central Asia"].alignment == "Neutral"):
          app.map["Central Asia"].markers.append("CRT")
          app.outputToHistory("CRT Maker added in Central Asia", True)
      elif self.number == 4: # Moro Talks
        app.markers.append("Moro Talks")
        app.outputToHistory("Moro Talks in play.", False)
        app.testCountry("Philippines")
        app.changeFunding(-1)
      elif self.number == 5: # NEST
        app.markers.append("NEST")
        app.outputToHistory("NEST in play. If jihadists have WMD, all plots in the US placed face up.", True)
      elif self.number == 6 or self.number == 7: # Sanctions
        if "Patriot Act" in app.markers:
          app.changeFunding(-2)
        else:
          return False
      elif self.number == 8 or self.number == 9 or self.number == 10: # Special Forces
        while True:
          input = app.getCountryFromUser("Remove a cell from what country that has troops or is adjacent to a country with troops (? for list)?: ",  "XXX", app.listCountriesWithCellAndAdjacentTroops)
          if input == "":
            print("")
            return
          else:
            if app.map[input].totalCells(True) <= 0:
              print("There are no cells in %s\n" % input)
            else:
              foundTroops = False
              for country in app.map:
                if country == input or app.isAdjacent(input, country):
                  if app.map[country].troops() > 0:
                    foundTroops = True
                    break
              if not foundTroops:
                print("Neither this or any adjacent country have troops.\n")
              else:
                app.removeCell(input)
                app.outputToHistory(app.board.country_summary(input), True)
                break
      elif self.number == 11: # Abbas
        numIRIsrael = 0
        for country in app.map:
          if app.isAdjacent(country, "Israel"):
            if app.map[country].islamist_rule_Q():
              numIRIsrael = 1
              break
        app.markers.append("Abbas")
        app.outputToHistory("Abbas in play.", False)
        if app.troops >= 5 and numIRIsrael <= 0:
          app.changePrestige(1, False)
          app.changeFunding(-2, True)
      elif self.number == 12: # Al-Azhar
        app.testCountry("Egypt")
        numIR = app.numIslamicRule()
        if numIR <= 0:
          app.changeFunding(-4, True)
        else:
          app.changeFunding(-2, True)
      elif self.number == 13: # Anbar Awakening
        if (app.map["Iraq"].troops() > 0) or (app.map["Syria"].troops() > 0):
          app.markers.append("Anbar Awakening")
          app.outputToHistory("Anbar Awakening in play.", False)
          if app.map["Iraq"].troops() == 0:
            app.map["Syria"].aid = 1
            app.outputToHistory("Aid in Syria.", False)
          elif app.map["Syria"].troops() == 0:
            app.map["Iraq"].aid = 1
            app.outputToHistory("Aid in Iraq.", False)
          else:
            print("There are troops in both Iraq and Syria.")
            if app.getYesNoFromUser("Do you want to add the Aid to Iraq? (y/n): "):
              app.map["Iraq"].aid = 1
              app.outputToHistory("Aid in Iraq.", False)
            else:
              app.map["Syria"].aid = 1
              app.outputToHistory("Aid in Syria.", False)
          app.changePrestige(1, False)
          print("")
        else:
          return False
      elif self.number == 14: # Covert Action
        targetCountry = ""
        numAdv = 0
        for country in app.map:
          if app.map[country].alignment == "Adversary":
            targetCountry = country
            numAdv += 1
        if numAdv == 0:
          return False
        elif numAdv > 1:
          while True:
            input = app.getCountryFromUser("Choose an Adversary country to attempt Covert Action (? for list): ",  "XXX", app.listAdversaryCountries)
            if input == "":
              print("")
              return
            else:
              if app.map[input].alignment != "Adversary":
                print("%s is not an Adversary.\n" % input)
              else:
                targetCountry = input
                break
        actionRoll = app.getRollFromUser("Enter Covert Action roll or r to have program roll: ")
        if actionRoll >= 4:
          app.map[targetCountry].alignment = "Neutral"
          app.outputToHistory("Covert Action successful, %s now Neutral." % targetCountry, False)
          app.outputToHistory(app.board.country_summary(input), True)
        else:
          app.outputToHistory("Covert Action fails.", True)
      elif self.number == 15: # Ethiopia Strikes
        if (app.map["Somalia"].islamist_rule_Q()) or (app.map["Sudan"].islamist_rule_Q()):
          if app.map["Somalia"].governance != 4:
            app.map["Sudan"].governance = 3
            app.map["Sudan"].alignment = "Neutral"
            app.outputToHistory("Sudan now Poor Neutral.", False)
            app.outputToHistory(app.board.country_summary("Sudan"), True)
          elif app.map["Sudan"].governance != 4:
            app.map["Somalia"].governance = 3
            app.map["Somalia"].alignment = "Neutral"
            app.outputToHistory("Somalia now Poor Neutral.", False)
            app.outputToHistory(app.board.country_summary("Somalia"), True)
          else:
            print("Both Somalia and Sudan are under Islamic Rule.")
            if app.getYesNoFromUser("Do you want Somalia to be set to Poor Neutral? (y/n): "):
              app.map["Somalia"].governance = 3
              app.map["Somalia"].alignment = "Neutral"
              app.outputToHistory("Somalia now Poor Neutral.", False)
              app.outputToHistory(app.board.country_summary("Somalia"), True)
            else:
              app.map["Sudan"].governance = 3
              app.map["Sudan"].alignment = "Neutral"
              app.outputToHistory("Sudan now Poor Neutral.", False)
              app.outputToHistory(app.board.country_summary("Sudan"), True)
          print("")
        else:
          return False
      elif self.number == 16: # Euro-Islam
        posStr = app.getPostureFromUser("Select Benelux's Posture (hard or soft): ")
        app.executeCardEuroIslam(posStr)
      elif self.number == 17: # FSB
        app.outputToHistory("Examine Jihadist hand for Loose Nukes, HEU, or Kazakh Strain.", False)
        hasThem = app.getYesNoFromUser("Does the Jihadist hand have Loose Nukes, HEU, or Kazakh Strain? (y/n): ")
        if hasThem:
          app.outputToHistory("Discard Loose Nukes, HEU, or Kazakh Strain from the Jihadist hand.", False)
        else:
          russiaCells = app.map["Russia"].totalCells(True)
          cenAsiaCells = app.map["Central Asia"].totalCells(True)
          if russiaCells > 0 or cenAsiaCells > 0:
            if russiaCells == 0:
              app.removeCell("Central Asia")
              app.outputToHistory(app.board.country_summary("Central Asia"), True)
            elif cenAsiaCells == 0:
              app.removeCell("Russia")
              app.outputToHistory(app.board.country_summary("Russia"), True)
            else:
              isRussia = app.getYesNoFromUser("There are cells in both Russia and Central Asia. Do you want to remove a cell in Russia? (y/n): ")
              if isRussia:
                app.removeCell("Russia")
                app.outputToHistory(app.board.country_summary("Russia"), True)
              else:
                app.removeCell("Central Asia")
                app.outputToHistory(app.board.country_summary("Central Asia"), False)
          else:
            app.outputToHistory("There are no cells in Russia or Central Asia.", False)
        app.outputToHistory("Shuffle Jihadist hand.", True)
      elif self.number == 18: # Intel Community
        app.outputToHistory("Examine Jihadist hand.  Do not change order of cards.", False)
        app.outputToHistory("Conduct a 1-value operation (Use commands: alert, deploy, disrupt, reassessment, regime, withdraw, or woi).", False)
        app.outputToHistory("You may now interrupt this action phase to play another card (Use the u command).", True)
      elif self.number == 19: # Kemalist Republic
        app.outputToHistory("Turkey now a Fair Ally.", False)
        app.map["Turkey"].governance = 2
        app.map["Turkey"].alignment = "Ally"
        app.outputToHistory(app.board.country_summary("Turkey"), True)
      elif self.number == 20: # King Abdullah
        app.outputToHistory("Jordan now a Fair Ally.", False)
        app.map["Jordan"].governance = 2
        app.map["Jordan"].alignment = "Ally"
        app.outputToHistory(app.board.country_summary("Jordan"), True)
        app.changePrestige(1)
        app.changeFunding(-1)
      elif self.number == 21: # Let's Roll
        while True:
          plotCountry = app.getCountryFromUser("Draw a card.  Choose an Ally or Good country to remove a plot from (? for list): ", "XXX", app.listGoodAllyPlotCountries)
          if plotCountry == "":
            print("")
            return
          else:
            if app.map[plotCountry].governance != 1 and app.map[plotCountry].alignment != "Ally":
              print("%s is not Good or an Ally." % plotCountry)
              print("")
            elif app.map[plotCountry].plots <= 0:
              print("%s has no plots." % plotCountry)
              print("")
            else:
              while True:
                postureCountry = app.getCountryFromUser("Now choose a non-US country to set its Posture: ", "XXX", None)
                if postureCountry == "":
                  print("")
                  return
                else:
                  if postureCountry == "United States":
                    print("Choos a non-US country.")
                    print("")
                  else:
                    postureStr = app.getPostureFromUser("What Posture should %s have (h or s)? " % postureCountry)
                    app.executeCardLetsRoll(plotCountry, postureCountry, postureStr)
                    return
      elif self.number == 22: # Mossad and Shin Bet
        app.removeAllCellsFromCountry("Israel")
        app.removeAllCellsFromCountry("Jordan")
        app.removeAllCellsFromCountry("Lebanon")
        app.outputToHistory("", False)
      elif self.number == 23 or self.number == 24 or self.number == 25: # Predator
        while True:
          input = app.getCountryFromUser("Choose non-Iran Muslim Country to remove a cell from (? for list): ", "XXX", app.listMuslimCountriesWithCells)
          if input == "":
            print("")
            return
          else:
            if app.map[input].totalCells(True) == 0:
              print("%s has no cells." % input)
              print("")
            elif app.map[input].iran_Q():
              print("Iran is not allowed.")
              print("")
            elif app.map[input].non_muslim_Q():
              print("Choose a Muslim country.")
              print("")
            else:
              app.removeCell(input)
              app.outputToHistory(app.board.country_summary(input), True)
              break
      elif self.number == 26: # Quartet
        if not "Abbas" in app.markers:
          return False
        if app.troops <= 4:
          return False
        for country in app.map:
          if app.isAdjacent(country, "Israel"):
            if app.map[country].islamist_rule_Q():
              return False
        app.changePrestige(2)
        app.changeFunding(-3)
        app.outputToHistory("", False)
      elif self.number == 27: # Saddam Captured
        if app.map["Iraq"].troops() == 0:
          return False
        app.markers.append("Saddam Captured")
        app.map["Iraq"].aid = 1
        app.outputToHistory("Aid added in Iraq", False)
        app.changePrestige(1)
        app.outputToHistory(app.board.country_summary("Iraq"), True)
      elif self.number == 28: # Sharia
        numBesieged = app.numBesieged()
        target = ""
        if numBesieged <= 0:
          return False
        elif numBesieged == 1:
          for country in app.map:
            if app.map[country].besieged > 0:
              target = country
              break
        else:
          while True:
            input = app.getCountryFromUser("Choose a country with a Besieged Regime marker to remove (? for list): ",  "XXX", app.listBesiegedCountries)
            if input == "":
              print("")
              return
            else:
              if app.map[input].besieged <= 0:
                print("%s is not a Besieged Regime." % input)
                print("")
              else:
                target = input
                break
        app.map[target].besieged = 0
        app.outputToHistory("%s is no longer a Besieged Regime." % target, False)
        app.outputToHistory(app.board.country_summary(target), True)
      elif self.number == 29: # Tony Blair
        app.board.set_posture("United Kingdom", app.map["United States"].posture)
        app.outputToHistory("United Kingdom posture now %s" % app.map["United Kingdom"].posture, False)
        print("You may roll War of Ideas in up to 3 Schengen countries.")
        for i in range(3):
          target = ""
          finishedPicking = False
          while not target:
            input = app.getCountryFromUser("Choose Schengen country to make a WOI roll (done to stop rolling) (? for list)?: ",  "done", app.listSchengenCountries)
            if input == "":
              print("")
              return
            elif input == "done":
              finishedPicking = True
              break
            else:
              if not app.map[input].schengen:
                print("%s is not a Schengen country." % input)
                print("")
                return
              else:
                target = input
                postureRoll = app.getRollFromUser("Enter Posture Roll or r to have program roll: ")
                app.executeNonMuslimWOI(target, postureRoll)
          if finishedPicking:
            break
        app.outputToHistory("", False)
      elif self.number == 30: # UN Nation Building
        numRC = app.numRegimeChange()
        if (numRC <= 0) or ("Vieira de Mello Slain" in app.markers):
          return False
        target = ""
        if numRC == 1:
          for country in app.map:
            if app.map[country].regime_change > 0:
              target = country
              break
        else:
          while True:
            input = app.getCountryFromUser("Choose a Regime Change country (? for list): ",  "XXX", app.listRegimeChangeCountries)
            if input == "":
              print("")
              return
            else:
              if app.map[input].regime_change <= 0:
                print("%s is not a Regime Change country." % input)
                print("")
              else:
                target = input
                break
        app.map[target].aid = 1
        app.outputToHistory("Aid added to %s." % target, False)
        woiRoll = app.getRollFromUser("Enter WOI Roll or r to have program roll: ")
        modRoll = app.modifiedWoIRoll(woiRoll, target, False)
        app.handleMuslimWoI(modRoll, target)
      elif self.number == 31: # Wiretapping
        if "Leak-Wiretapping" in app.markers:
          return False
        for country in ["United States", "United Kingdom", "Canada"]:
          if app.map[country].active_cells > 0:
            num = app.map[country].activeCells
            if num > 0:
              app.map[country].active_cells -= num
              app.cells += num
              app.outputToHistory("%d Active Cell(s) removed from %s." % (num, country), False)
          if app.map[country].sleeper_cells > 0:
            num = app.map[country].sleeper_cells
            if num > 0:
              app.map[country].sleeper_cells -= num
              app.cells += num
              app.outputToHistory("%d Sleeper Cell(s) removed from %s." % (num, country), False)
          if app.board.cadre_Q(country):
            num = app.map[country].cadre
            if num > 0:
              app.board.remove_cadre(country)
              app.outputToHistory("Cadre removed from %s." % country, False)
          if app.map[country].plots > 0:
            num = app.map[country].plots
            if num > 0:
              app.map[country].plots -= num
              app.outputToHistory("%d Plots remove(d) from %s." % (num, country), False)
        app.markers.append("Wiretapping")
        app.outputToHistory("Wiretapping in Play.", True)
      elif self.number == 32: # Back Channel
        if app.map["United States"].hard_Q():
          return False
        numAdv = app.numAdversary()
        if numAdv <= 0:
          return False
        if app.getYesNoFromUser("Do you want to discard a card with a value that exactly matches an Adversary's Resources? (y/n): "):
          while True:
            input = app.getCountryFromUser("Choose an Adversary country (? for list): ",  "XXX", app.listAdversaryCountries)
            if input == "":
              print("")
              return False
            else:
              if app.map[input].alignment != "Adversary":
                print("%s is not a Adversary country." % input)
                print("")
              else:
                app.map[input].alignment = "Neutral"
                app.outputToHistory("%s now Neutral" % input, False)
                app.map[input].aid = 1
                app.outputToHistory("Aid added to %s." % input, False)
                app.outputToHistory(app.board.country_summary(input), True)
                break
      elif self.number == 33: # Benazir Bhutto
        app.markers.append("Benazir Bhutto")
        app.outputToHistory("Benazir Bhutto in Play.", False)
        if app.map["Pakistan"].poor_Q():
          app.map["Pakistan"].governance = 2
          app.outputToHistory("Pakistan now Fair governance.", False)
        app.outputToHistory("No Jihads in Pakistan.", False)
        app.outputToHistory(app.board.country_summary("Pakistan"), True)
      elif self.number == 34: # Enhanced Measures
        app.markers.append("Enhanced Measures")
        app.outputToHistory("Enhanced Measures in Play.", False)
        app.outputToHistory("Take a random card from the Jihadist hand.", False)
        app.do_disrupt("")
        app.outputToHistory("", False)
      elif self.number == 35: # Hajib
        app.testCountry("Turkey")
        app.map["Turkey"].governance -= 1
        app.outputToHistory("Turkey Governance now %s." % app.map["Turkey"].govStr(), False)
        app.changeFunding(-2)
        posStr = app.getPostureFromUser("Select Frances's Posture (hard or soft): ")
        app.board.set_posture("France", posStr)
        app.outputToHistory(app.board.country_summary("Turkey"), False)
        app.outputToHistory(app.board.country_summary("France"), True)
      elif self.number == 36: # Indo-Pakistani Talks
        app.markers.append("Indo-Pakistani Talks")
        app.outputToHistory("Indo-Pakistani Talks in Play.", False)
        app.map['Pakistan'].alignment = "Ally"
        app.outputToHistory("Pakistan now Ally", False)
        posStr = app.getPostureFromUser("Select India's Posture (hard or soft): ")
        app.board.set_posture("India", posStr)
        app.outputToHistory(app.board.country_summary("Pakistan"), False)
        app.outputToHistory(app.board.country_summary("India"), True)
      elif self.number == 37: # Iraqi WMD
        app.markers.append("Iraqi WMD")
        app.outputToHistory("Iraqi WMD in Play.", False)
        app.outputToHistory("Use this or a later card for Regime Change in Iraq at any Governance.", True)
      elif self.number == 38: # Libyan Deal
        app.markers.append("Libyan Deal")
        app.outputToHistory("Libyan Deal in Play.", False)
        app.map["Libya"].ally_Q()
        app.outputToHistory("Libya now Ally", False)
        app.changePrestige(1)
        print("Select the Posture of 2 Schengen countries.")
        for i in range(2):
          target = ""
          while not target:
            input = app.getCountryFromUser("Choose Schengen country (? for list)?: ", "XXX", app.listSchengenCountries)
            if input == "":
              print("")
            else:
              if not app.map[input].schengen:
                print("%s is not a Schengen country." % input)
                print("")
                return
              else:
                target = input
                posStr = app.getPostureFromUser("Select %s's Posture (hard or soft): " % target)
                app.board.set_posture(target, posStr)
                app.outputToHistory(app.board.country_summary(target), False)
        app.outputToHistory("", False)
      elif self.number == 39: # Libyan WMD
        app.markers.append("Libyan WMD")
        app.outputToHistory("Libyan WMD in Play.", False)
        app.outputToHistory("Use this or a later card for Regime Change in Libya at any Governance.", True)
      elif self.number == 40: # Mass Turnout
        numRC = app.numRegimeChange()
        target = ""
        if numRC <= 0:
          return False
        elif numRC == 1:
          for country in app.map:
            if app.map[country].regime_change > 0:
              target = country
              break
        else:
          while True:
            input = app.getCountryFromUser("Choose a Regime Change Country to improve governance (? for list): ",  "XXX", app.listRegimeChangeCountries)
            if input == "":
              print("")
              return
            else:
              if app.map[input].regime_change <= 0:
                print("%s is not a Regime Change country." % input)
                print("")
              else:
                target = input
                break
        app.improveGovernance(target)
        app.outputToHistory("%s Governance improved." % target, False)
        app.outputToHistory(app.board.country_summary(target), True)
      elif self.number == 41: # NATO
        numRC = app.numRegimeChange()
        target = ""
        if numRC <= 0:
          return False
        elif numRC == 1:
          for country in app.map:
            if app.map[country].regime_change > 0:
              target = country
              break
        else:
          while True:
            input = app.getCountryFromUser("Choose a Regime Change Country to land NATO troops (? for list): ",  "XXX", app.listRegimeChangeCountries)
            if input == "":
              print("")
              return
            else:
              if app.map[input].regime_change <= 0:
                print("%s is not a Regime Change country." % input)
                print("")
              else:
                target = input
                break
        app.map[target].markers.append("NATO")
        app.outputToHistory("NATO added in %s" % target, False)
        app.map[target].aid = 1
        app.outputToHistory("Aid added in %s" % target, False)
        app.outputToHistory(app.board.country_summary(target), True)
      elif self.number == 42: # Pakistani Offensive
        if "FATA" in app.map["Pakistan"].markers:
          app.map["Pakistan"].markers.remove("FATA")
          app.outputToHistory("FATA removed from Pakistan", True)
      elif self.number == 43: # Patriot Act
        app.markers.append("Patriot Act")
      elif self.number == 44: # Renditions
        app.markers.append("Renditions")
        app.outputToHistory("Renditions in Play.", False)
        app.outputToHistory("Discard a random card from the Jihadist hand.", False)
        if app.numDisruptable() > 0:
          app.do_disrupt("")
        app.outputToHistory("", False)
      elif self.number == 45: # Safer Now
        app.changePrestige(3)
        postureRoll = app.getRollFromUser("Enter US Posture Roll or r to have program roll: ")
        if postureRoll <= 4:
          app.board.set_posture("United States", "Soft")
          app.outputToHistory("US Posture now Soft.", False)
        else:
          app.board.set_posture("United States", "Hard")
          app.outputToHistory("US Posture now Hard.", False)
        while True:
          postureCountry = app.getCountryFromUser("Now choose a non-US country to set its Posture: ", "XXX", None)
          if postureCountry == "":
            print("")
          else:
            if postureCountry == "United States":
              print("Choos a non-US country.")
              print("")
            else:
              postureStr = app.getPostureFromUser("What Posture should %s have (h or s)? " % postureCountry)
              app.outputToHistory("%s Posture now %s" % (postureCountry, postureStr), False)
              app.board.set_posture(postureCountry, postureStr)
              app.outputToHistory(app.board.country_summary("United States"), False)
              app.outputToHistory(app.board.country_summary(postureCountry), True)
              break
      elif self.number == 46: # Sistani
        targetCountries = []
        for country in app.map:
          if app.map[country].shia_mix_Q():
            if app.map[country].regime_change > 0:
              if (app.map[country].totalCells(True)) > 0:
                targetCountries.append(country)
        if len(targetCountries) == 1:
          target = targetCountries[0]
        else:
          target = None
        while not target:
          input = app.getCountryFromUser("Choose a Shia-Mix Regime Change Country with a cell to improve governance (? for list): ",  "XXX", app.listShiaMixRegimeChangeCountriesWithCells)
          if input == "":
            print("")
          else:
            if input not in targetCountries:
              print("%s is not a Shi-Mix Regime Change Country with a cell." % input)
              print("")
            else:
              target = input
              break
        app.improveGovernance(target)
        app.outputToHistory("%s Governance improved." % target, False)
        app.outputToHistory(app.board.country_summary(target), True)
      elif self.number == 47: # The door of Itjihad was closed
        app.lapsing.append("The door of Itjihad was closed")
      else:
        return False
    elif self.type == "Jihadist" and side == "Jihadist":
      if self.number == 48: # Adam Gadahn
        cardNum = app.getCardNumFromUser("Enter the number of the next Jihadist card or none if there are none left: ")
        if cardNum == "none":
          app.outputToHistory("No cards left to recruit to US.", True)
          app.outputToHistory("Jihadist Activity Phase findshed, enter plot command.", True)
          return
        ops = app.deck[str(cardNum)].ops
        rolls = []
        for i in range(ops):
          rolls.append(random.randint(1,6))
        app.outputToHistory("Jihadist Activity Phase findshed, enter plot command.", True)
        app.executeRecruit("United States", ops, rolls, 2)
      elif self.number == 49: # Al-Ittihad al-Islami
        app.placeCells("Somalia", 1)
      elif self.number == 50: # Ansar al-Islam
        possible = ["Iraq", "Iran"]
        target = random.choice(possible)
        app.placeCells(target, 1)
      elif self.number == 51: # FREs
        if "Saddam Captured" in app.markers:
          cellsToMove = 2
        else:
          cellsToMove = 4
        cellsToMove = min(cellsToMove, app.cells)
        app.placeCells("Iraq", cellsToMove)
      elif self.number == 52: # IDEs
        app.outputToHistory("US randomly discards one card.", True)
      elif self.number == 53: # Madrassas
        app.handleRecruit(1, True)
        cardNum = app.getCardNumFromUser("Enter the number of the next Jihadist card or none if there are none left: ")
        if cardNum == "none":
          app.outputToHistory("No cards left to recruit.", True)
          app.outputToHistory("Jihadist Activity Phase findshed, enter plot command.", True)
          return
        ops = app.deck[str(cardNum)].ops
        app.handleRecruit(ops, True)
        app.outputToHistory("Jihadist Activity Phase findshed, enter plot command.", True)
      elif self.number == 54: # Moqtada al-Sadr
        app.map["Iraq"].markers.append("Sadr")
        app.outputToHistory("Sadr Maker added in Iraq", True)
      elif self.number == 55: # Uyghur Jihad
        app.testCountry("China")
        if app.cells > 0:
          if app.map["China"].soft_Q():
            app.map["China"].sleeper_cells += 1
            app.cells -= 1
            app.outputToHistory("Sleeper Cell placed in China", False)
            app.outputToHistory(app.board.country_summary("China"), True)
          else:
            app.testCountry("Central Asia")
            app.map["Central Asia"].sleeper_cells += 1
            app.cells -= 1
            app.outputToHistory("Sleeper Cell placed in Central Asia", False)
            app.outputToHistory(app.board.country_summary("Central Asia"), True)
        else:
          app.outputToHistory("No cells to place.", True)
      elif self.number == 56: # Vieira de Mello Slain
        app.markers.append("Vieira de Mello Slain")
        app.outputToHistory("Vieira de Mello Slain in play.", False)
        app.changePrestige(-1)
      elif self.number == 57: # Abu Sayyaf
        app.placeCells("Philippines", 1)
        app.markers.append("Abu Sayyaf")
      elif self.number == 58: # Al-Anbar
        app.markers.append("Al-Anbar")
        app.outputToHistory("Al-Anbar in play.", True)
        app.testCountry("Iraq")
        if app.cells > 0:
          app.map["Iraq"].sleeper_cells += 1
          app.cells -= 1
          app.outputToHistory("Sleeper Cell placed in Iraq", True)
      elif self.number == 59: # Amerithrax
        app.outputToHistory("US side discards its highest-value US-associated event card, if it has any.", True)
      elif self.number == 60: # Bhutto Shot
        app.markers.append("Bhutto Shot")
        app.outputToHistory("Bhutto Shot in play.", True)
      elif self.number == 61: # Detainee Release
        if app.cells > 0:
          target = None
          while not target:
            input = app.getCountryFromUser("Choose a country where Disrupt occured this or last Action Phase: ",  "XXX", None)
            if input == "":
              print("")
              return
            else:
              target = input
              break
          app.testCountry(target)
          app.map[target].sleeper_cells += 1
          app.cells -= 1
          app.outputToHistory("Sleeper Cell placed in %s" % target, False)
          app.outputToHistory(app.board.country_summary(target), True)
        app.outputToHistory("Draw a card for the Jihadist and put it on the top of their hand.", True)
      elif self.number == 62: # Ex-KGB
        if "CTR" in app.map["Russia"].markers:
          app.map["Russia"].markers.remove("CTR")
          app.outputToHistory("CTR removed from Russia.", True)
        else:
          targetCaucasus = False
          if app.map["Caucasus"].test_posture_Q() or app.map["Caucasus"].posture == app.map["United States"].posture:
            if app.board.gwot()['penalty'] == 0:
              cacPosture = app.map["Caucasus"].posture
              if app.map["United States"].hard_Q():
                app.board.set_posture("Caucasus", "Soft")
              else:
                app.board.set_posture("Caucasus", "Hard")
              if app.board.gwot()['penalty'] < 0:
                targetCaucasus = True
              app.board.set_posture("Caucasus", cacPosture)
          if targetCaucasus:
            if app.map["United States"].hard_Q():
              app.board.set_posture("Caucasus", "Soft")
            else:
              app.board.set_posture("Caucasus", "Hard")
            app.outputToHistory("Caucasus posture now %s" % app.map["Caucasus"].posture, False)
            app.outputToHistory(app.board.country_summary("Caucasus"), True)
          else:
            app.testCountry("Central Asia")
            if app.map["Central Asia"].ally_Q():
              app.map["Central Asia"].alignment = "Neutral"
              app.outputToHistory("Central Asia now Neutral.", True)
            elif app.map["Central Asia"].alignment == "Neutral":
              app.map["Central Asia"].alignment = "Adversary"
              app.outputToHistory("Central Asia now Adversary.", True)
            app.outputToHistory(app.board.country_summary("Central Asia"), True)
      elif self.number == 63: # Gaza War
        app.changeFunding(1)
        app.changePrestige(-1)
        app.outputToHistory("US discards a random card.", True)
      elif self.number == 64: # Hariri Killed
        app.testCountry("Lebanon")
        app.testCountry("Syria")
        app.map["Syria"].alignment = "Adversary"
        app.outputToHistory("Syria now Adversary.", False)
        if app.map["Syria"].governance < 3:
          app.worsenGovernance("Syria")
          app.outputToHistory("Governance in Syria worsened.", False)
          app.outputToHistory(app.board.country_summary("Syria"), True)
        app.outputToHistory(app.board.country_summary("Lebanon"), True)
      elif self.number == 65: # HEU
        possibles = []
        if app.map["Russia"].totalCells() > 0 and "CTR" not in app.map["Russia"].markers:
          possibles.append("Russia")
        if app.map["Central Asia"].totalCells() > 0 and "CTR" not in app.map["Central Asia"].markers:
          possibles.append("Central Asia")
        target = random.choice(possibles)
        roll = random.randint(1,6)
        app.executeCardHEU(target, roll)
      elif self.number == 66: # Homegrown
        app.placeCells("United Kingdom", 1)
      elif self.number == 67: # Islamic Jihad Union
        app.placeCells("Central Asia", 1)
        if app.cells > 0:
          app.placeCells("Afghanistan", 1)
      elif self.number == 68: # Jemaah Islamiya
        app.placeCells("Indonesia/Malaysia", 2)
      elif self.number == 69: # Kazakh Strain
        roll = random.randint(1,6)
        app.executeCardHEU("Central Asia", roll)
      elif self.number == 70: # Lashkar-e-Tayyiba
        app.placeCells("Pakistan", 1)
        if app.cells > 0:
          app.placeCells("India", 1)
      elif self.number == 71: # Loose Nuke
        roll = random.randint(1,6)
        app.executeCardHEU("Russia", roll)
      elif self.number == 72: # Opium
        cellsToPlace = min(app.cells, 3)
        if app.map["Afghanistan"].islamist_rule_Q():
          cellsToPlace = app.cells
        app.placeCells("Afghanistan", cellsToPlace)
      elif self.number == 73: # Pirates
        app.markers.append("Pirates")
        app.outputToHistory("Pirates in play.", False)
      elif self.number == 74: # Schengen Visas
        if app.cells == 15:
          app.outputToHistory("No cells to travel.", False)
          return
        app.handleTravel(2, False, True)
      elif self.number == 75: # Schroeder & Chirac
        app.board.set_posture("Germany", "Soft")
        app.outputToHistory("%s Posture now %s" % ("Germany", app.map["Germany"].posture), True)
        app.board.set_posture("France", "Soft")
        app.outputToHistory("%s Posture now %s" % ("France", app.map["France"].posture), True)
        app.changePrestige(-1)
      elif self.number == 76: # Abu Ghurayb
        app.outputToHistory("Draw 2 cards.", False)
        app.changePrestige(-2)
        allys = app.minorJihadInGoodFairChoice(1, True)
        if not allys:
          app.outputToHistory("No Allys to shift.", True)
        else:
          target = allys[0][0]
          app.map[target].alignment = "Neutral"
          app.outputToHistory("%s Alignment shifted to Neutral." % target, True)
      elif self.number == 77: # Al Jazeera
        choices = app.minorJihadInGoodFairChoice(1, False, True)
        if not choices:
          app.outputToHistory("No countries to shift.", True)
        else:
          target = choices[0][0]
          if app.map[target].ally_Q():
            app.map[target].alignment = "Neutral"
          elif app.map[target].alignment == "Neutral":
            app.map[target].alignment = "Adversary"
          app.outputToHistory("%s Alignment shifted to %s." % (target, app.map[target].alignment), True)
      elif self.number == 78: # Axis of Evil
        app.outputToHistory("US discards any Iran, Hizballah, or Jaysh al-Mahdi cards from hand.", False)
        if app.map["United States"].soft_Q():
          app.board.set_posture("United States", "Hard")
          app.outputToHistory("US Posture now Hard.", False)
        prestigeRolls = []
        for i in range(3):
          prestigeRolls.append(random.randint(1,6))
        presMultiplier = 1
        if prestigeRolls[0] <= 4:
          presMultiplier = -1
        app.changePrestige(min(prestigeRolls[1], prestigeRolls[2]) * presMultiplier)
      elif self.number == 79: # Clean Operatives
        app.handleTravel(2, False, False, True)
      elif self.number == 80: # FATA
        app.testCountry("Pakistan")
        app.map["Pakistan"].markers.append("FATA")
        app.outputToHistory("FATA Maker added in Pakistan", True)
        app.placeCells("Pakistan", 1)
      elif self.number == 81: # Foreign Fighters
        possibles = []
        for country in app.map:
          if app.map[country].regime_change > 0:
            possibles.append(country)
        if len(possibles) <= 0:
          return False
        target = random.choice(possibles)
        app.placeCells(target, 5)
        if app.map[target].aid > 0:
          app.map[target].aid = 0
          app.outputToHistory("Aid removed from %s" % target, False)
        else:
          app.map[target].besieged = 1
          app.outputToHistory("%s no Besieged Regime" % target, False)
        app.outputToHistory(app.board.country_summary(target), True)
      elif self.number == 82: # Jihadist Videos
        possibles = []
        for country in app.map:
          if app.map[country].totalCells() == 0:
            possibles.append(country)
        random.shuffle(possibles)
        for i in range(3):
          app.testCountry(possibles[i])
          # number of available cells does not matter for Jihadist Videos
          # if app.cells > 0:
          rolls = []
          rolls.append(random.randint(1,6))
          app.executeRecruit(possibles[i], 1, rolls, False, True)
      elif self.number == 83: # Kashmir
        app.placeCells("Pakistan", 1)
        if app.map["Pakistan"].ally_Q():
          app.map["Pakistan"].alignment = "Neutral"
        elif app.map["Pakistan"].alignment == "Neutral":
          app.map["Pakistan"].alignment = "Adversary"
        app.outputToHistory("%s Alignment shifted to %s." % ("Pakistan", app.map["Pakistan"].alignment), True)
        app.outputToHistory(app.board.country_summary("Pakistan"), True)
      elif self.number == 84 or self.number == 85: # Leak
        possibles = []
        if "Enhanced Measures" in app.markers:
          possibles.append("Enhanced Measures")
        if "Renditions" in app.markers:
          possibles.append("Renditions")
        if "Wiretapping" in app.markers:
          possibles.append("Wiretapping")
        target = random.choice(possibles)
        app.markers.remove(target)
        app.markers.append("Leak-"+target)
        app.outputToHistory("%s removed and can no longer be played." % target, False)
        usPrestigeRolls = []
        for i in range(3):
          usPrestigeRolls.append(random.randint(1,6))
        postureRoll = random.randint(1,6)

        presMultiplier = 1
        if usPrestigeRolls[0] <= 4:
          presMultiplier = -1
        app.changePrestige(min(usPrestigeRolls[1], usPrestigeRolls[2]) * presMultiplier, False)
        if postureRoll <= 4:
          app.board.set_posture("United States", "Soft")
        else:
          app.board.set_posture("United States", "Hard")
        app.outputToHistory("US Posture now %s" % app.map["United States"].posture, True)
      elif self.number == 86: # Lebanon War
        app.outputToHistory("US discards a random card.", False)
        app.changePrestige(-1, False)
        possibles = []
        for country in app.map:
          if app.map[country].shia_mix_Q():
            possibles.append(country)
        target = random.choice(possibles)
        app.placeCells(target, 1)
      elif self.number == 87 or self.number == 88 or self.number == 89: # Martyrdom Operation
        if app.executePlot(1, False, [1], True) == 1:
          app.outputToHistory("No plots could be placed.", True)
          app.handleRadicalization(app.deck[str(self.number)].ops)
      elif self.number == 90: # Quagmire
        app.board.set_posture("United States", "Soft")
        app.outputToHistory("US Posture now Soft.", False)
        app.outputToHistory("US randomly discards two cards and Jihadist plays them.", False)
        app.outputToHistory("Do this using the j # command for each card.", True)
      elif self.number == 91: # Regional al-Qaeda
        possibles = []
        for country in app.map:
          if app.map[country].suni_Q() or app.map[country].shia_mix_Q():
            if app.map[country].governance == 0:
              possibles.append(country)
        random.shuffle(possibles)
        app.placeCells(possibles[0], 1)
        app.placeCells(possibles[1], 1)
      elif self.number == 92: # Saddam
        app.funding = 9
        app.outputToHistory("Jihadist Funding now 9.", True)
      elif self.number == 93: # Taliban
        app.testCountry("Afghanistan")
        app.map["Afghanistan"].besieged = 1
        app.outputToHistory("Afghanistan is now a Besieged Regime.", False)
        app.placeCells("Afghanistan", 1)
        app.placeCells("Pakistan", 1)
        if (app.map["Afghanistan"].islamist_rule_Q()) or (app.map["Pakistan"].islamist_rule_Q()):
          app.changePrestige(-3)
        else:
          app.changePrestige(-1)
      elif self.number == 94: # The door of Itjihad was closed
        target = None
        while not target:
          input = app.getCountryFromUser("Choose a country tested or improved to Fair or Good this or last Action Phase: ",  "XXX", None)
          if input == "":
            print("")
          elif app.map[input].governance != 2 and   app.map[input].governance != 1:
            print("%s is not Fair or Good.")
          else:
            target = input
            break
        app.map[target].governance += 1
        app.outputToHistory("%s Governance worsened." % target, False)
        app.outputToHistory(app.board.country_summary(target), True)
      elif self.number == 95: # Wahhabism
        if app.map["Saudi Arabia"].islamist_rule_Q():
          app.changeFunding(9)
        else:
          app.changeFunding(app.map["Saudi Arabia"].governance)
    else:
      if self.number == 96: # Danish Cartoons
        posStr = app.getPostureFromUser("Select Scandinavia's Posture (hard or soft): ")
        app.board.set_posture("Scandinavia", posStr)
        app.outputToHistory("Scandinavia posture now %s." % posStr, False)
        possibles = []
        for country in app.map:
          if app.map[country].suni_Q() or app.map[country].shia_mix_Q():
            if app.map[country].governance != 4:
              possibles.append(country)
        target = random.choice(possibles)
        app.testCountry(target)
        if app.numIslamicRule() > 0:
          app.outputToHistory("Place any available plot in %s." % target, False)
        else:
          app.outputToHistory("Place a Plot 1 in %s." % target, False)
        app.map[target].plots += 1
      elif self.number == 97: # Fatwa
        app.outputToHistory("Trade random cards.", False)
        if side == "US":
          app.outputToHistory("Conduct a 1-value operation (Use commands: alert, deploy, disrupt, reassessment, regime, withdraw, or woi).", False)
        else:
          app.aiFlowChartMajorJihad(97)
      elif self.number == 98: # Gaza Withdrawl
        if side == "US":
          app.changeFunding(-1)
        else:
          app.placeCells("Israel", 1)
      elif self.number == 99: # HAMAS Elected
        app.outputToHistory("US selects and discards one card.", False)
        app.changePrestige(-1)
        app.changeFunding(-1)
      elif self.number == 100: # His Ut-Tahrir
        if app.troops >= 10:
          app.changeFunding(-2)
        elif app.troops < 5:
          app.changeFunding(2)
      elif self.number == 101: # Kosovo
        app.changePrestige(1)
        app.testCountry("Serbia")
        if app.map["United States"].soft_Q():
          app.board.set_posture("Serbia", "Hard")
        else:
          app.board.set_posture("Serbia", "Soft")
        app.outputToHistory("Serbia Posture now %s." %             app.map["Serbia"].posture, True)
      elif self.number == 102: # Former Soviet Union
        testRoll = random.randint(1,6)
        if testRoll <= 4:
          app.map["Central Asia"].governance = 3
        else:
          app.map["Central Asia"].governance = 2
        app.map["Central Asia"].alignment = "Neutral"
        app.outputToHistory("%s tested, governance %s" % (app.map["Central Asia"].name, app.map["Central Asia"].govStr()), False)
      elif self.number == 103: # Hizballah
        if side == "US":
          oneAway = []
          twoAway = []
          threeAway = []
          for countryObj in app.map["Lebanon"].links:
            oneAway.append(countryObj.name)
          for country in oneAway:
            for subCountryObj in app.map[country].links:
              if subCountryObj.name not in twoAway and subCountryObj.name not in oneAway and subCountryObj.name != "Lebanon":
                twoAway.append(subCountryObj.name)
          for country in twoAway:
            for subCountryObj in app.map[country].links:
              if subCountryObj.name not in threeAway and subCountryObj.name not in twoAway and subCountryObj.name not in oneAway and subCountryObj.name != "Lebanon":
                threeAway.append(subCountryObj.name)
          possibles = []
          for country in oneAway:
            if country not in possibles and app.map[country].totalCells(True) > 0 and app.map[country].shia_mix_Q():
              possibles.append(country)
          for country in twoAway:
            if country not in possibles and app.map[country].totalCells(True) > 0 and app.map[country].shia_mix_Q():
              possibles.append(country)
          for country in threeAway:
            if country not in possibles and app.map[country].totalCells(True) > 0 and app.map[country].shia_mix_Q():
              possibles.append(country)
          if len(possibles) <= 0:
            app.outputToHistory("No Shia-Mix countries with cells within 3 countries of Lebanon.", True)
            target = None
          elif len(possibles) == 1:
            target = possibles[0]
          else:
            target = None
            while not target:
              input = app.getCountryFromUser("Remove a cell from what Shia-Mix country within 3 countries of Lebanon (? for list)?: ",  "XXX", app.listCountriesInParam, possibles)
              if input == "":
                print("")
              else:
                if app.map[input].totalCells(True) <= 0:
                  print("There are no cells in %s" % input)
                  print("")
                elif input not in possibles:
                  print("%s not a Shia-Mix country within 3 countries of Lebanon." % input)
                  print("")
                else:
                  target = input
          if target:
            app.removeCell(target)
            app.outputToHistory(app.board.country_summary(target), True)
        else:
          app.testCountry("Lebanon")
          app.map["Lebanon"].governance = 3
          app.outputToHistory("Lebanon governance now Poor.", False)
          app.map["Lebanon"].alignment = "Neutral"
          app.outputToHistory("Lebanon alignment now Neutral.", True)
      elif self.number == 104 or self.number == 105: # Iran
        if side == "US":
          target = None
          while not target:
            input = app.getCountryFromUser("Choose a Shia-Mix country to test. You can then remove a cell from there or Iran (? for list)?: ",  "XXX", app.listShiaMixCountries)
            if input == "":
              print("")
            else:
              if app.map[input].culture != "Shia-Mix":
                print("%s is not a Shia-Mix country." % input)
                print("")
              else:
                target = input
          picked = target
          app.testCountry(picked)
          if app.map["Iran"].totalCells(True) > 0:
            target = None
            while not target:
              input = app.getCountryFromUser("Remove a cell from %s or %s: " % (picked, "Iran"),  "XXX", None)
              if input == "":
                print("")
              else:
                if input != picked and input != "Iran":
                  print("Remove a cell from %s or %s: " % (picked, "Iran"))
                  print("")
                else:
                  target = input
          else:
            target = picked
          app.removeCell(target)
          app.outputToHistory(app.board.country_summary(target), True)
        else:
          possibles = []
          for country in app.map:
            if app.map[country].shia_mix_Q():
              possibles.append(country)
          target = random.choice(possibles)
          app.testCountry(target)
          tested = target
          target = None
          goods = []
          for country in app.map:
            if app.map[country].shia_mix_Q() or app.map[country].suni_Q():
              if app.map[country].good_Q():
                goods.append(country)
          if len(goods) > 1:
            distances = []
            for country in goods:
              distances.append((app.countryDistance(tested, country), country))
            distances.sort()
            target = distances[0][1]
          elif len(goods) == 1:
            target = goods[0]
          else:
            fairs = []
            for country in app.map:
              if app.map[country].shia_mix_Q() or app.map[country].suni_Q():
                if app.map[country].fair_Q():
                  fairs.append(country)
            if len(fairs) > 1:
              distances = []
              for country in fairs:
                distances.append((app.countryDistance(tested, country), country))
              distances.sort()
              target = distances[0][1]
            elif len(fairs) == 1:
              target = fairs[0]
            else:
              app.outputToHistory("No Good or Fair countries to Jihad in.", True)
              return
          app.outputToHistory("%s selected for jihad rolls." % target, False)
          for i in range(2):
            droll = random.randint(1,6)
            app.outputToHistory("Rolled: " + str(droll), False)
            if droll <= app.map[target].governance:
              if app.map[target].governance < 3:
                app.map[target].governance += 1
                app.outputToHistory("Governance worsened in %s." % target, False)
                app.outputToHistory(app.board.country_summary(target), True)
            else:
              app.outputToHistory("Roll failed.  No change to governance in %s." % target, False)

      elif self.number == 106: # Jaysh al-Mahdi
        if side == "US":
          target = None
          possibles = []
          for country in app.map:
            if app.map[country].shia_mix_Q():
              if app.map[country].troops() > 0 and app.map[country].totalCells() > 0:
                possibles.append(country)
          if len(possibles) == 1:
            target = possibles[0]
          while not target:
            input = app.getCountryFromUser("Choose a Shia-Mix country with cells and troops (? for list)?: ",  "XXX", app.listShiaMixCountriesWithCellsTroops)
            if input == "":
              print("")
            else:
              if input not in possibles:
                print("%s is not a Shia-Mix country with cells and troops." % input)
                print("")
              else:
                target = input
          app.removeCell(target)
          app.removeCell(target)
          app.outputToHistory(app.board.country_summary(target), True)
        else:
          possibles = []
          for country in app.map:
            if app.map[country].shia_mix_Q():
              possibles.append(country)
          target = random.choice(possibles)
          app.testCountry(target)
          tested = target
          target = None
          goods = []
          for country in app.map:
            if app.map[country].shia_mix_Q() or app.map[country].suni_Q():
              if app.map[country].good_Q():
                goods.append(country)
          if len(goods) > 1:
            distances = []
            for country in goods:
              distances.append((app.countryDistance(tested, country), country))
            distances.sort()
            target = distances[0][1]
          elif len(goods) == 1:
            target = goods[0]
          else:
            fairs = []
            for country in app.map:
              if app.map[country].shia_mix_Q() or app.map[country].suni_Q():
                if app.map[country].fair_Q():
                  fairs.append(country)
            if len(fairs) > 1:
              distances = []
              for country in fairs:
                distances.append((app.countryDistance(tested, country), country))
              distances.sort()
              target = distances[0][1]
            elif len(fairs) == 1:
              target = fairs[0]
            else:
              app.outputToHistory("No Good or Fair countries to Jihad in.", True)
              return
            if app.map[target].governance < 4:
              app.map[target].governance += 1
              app.outputToHistory("Governance worsened in %s." % target, False)
              app.outputToHistory(app.board.country_summary(target), True)
      elif self.number == 107: # Kurdistan
        if side == "US":
          app.testCountry("Iraq")
          app.map["Iraq"].aid = 1
          app.outputToHistory("Aid added to Iraq.", False)
          app.outputToHistory(app.board.country_summary("Iraq"), True)
        else:
          app.testCountry("Turkey")
          target = None
          possibles = []
          if app.map["Turkey"].governance < 3:
            possibles.append("Turkey")
          if app.map["Iraq"].governance != 0 and app.map["Iraq"].governance < 3:
            possibles.append("Iraq")
          if len(possibles) == 0:
            app.outputToHistory("Iraq and Lebanon cannot have governance worssened.", True)
            return
          elif len(possibles) == 0:
            target = possibles[0]
          else:
            countryScores = {}
            for country in possibles:
              countryScores[country] = 0
              if app.map[country].aid > 0:
                countryScores[country] += 10000
              if app.map[country].besieged > 0:
                countryScores[country] += 1000
              countryScores[country] += (app.countryResources(country) * 100)
              countryScores[country] += random.randint(1,99)
            countryOrder = []
            for country in countryScores:
              countryOrder.append((countryScores[country], (app.map[country].totalCells(True)), country))
            countryOrder.sort()
            countryOrder.reverse()
            target = countryOrder[0][2]
          app.map[target].governance += 1
          app.outputToHistory("Governance worsened in %s." % target, False)
          app.outputToHistory(app.board.country_summary(target), True)
      elif self.number == 108: # Musharraf
        app.removeCell("Pakistan")
        app.map["Pakistan"].governance = 3
        app.map["Pakistan"].alignment = "Ally"
        app.outputToHistory("Pakistan now Poor Ally.", False)
        app.outputToHistory(app.board.country_summary("Pakistan"), True)
      elif self.number == 109: # Tora Bora
        possibles = []
        for country in app.map:
          if app.map[country].regime_change > 0:
            if app.map[country].totalCells() >= 2:
              possibles.append(country)
        target = None
        if len(possibles) == 0:
          return False
        if len(possibles) == 1:
          target = possibles[0]
        else:
          if side == "US":
            app.outputToHistory("US draws one card.", False)
            while not target:
              input = app.getCountryFromUser("Choose a Regime Change country with at least 2 troops. (? for list)?: ",  "XXX", app.listRegimeChangeWithTwoCells)
              if input == "":
                print("")
              else:
                if input not in possibles:
                  print("%s is not a Regime Change country with at least 2 troops." % input)
                  print("")
                else:
                  target = input
          else:
            app.outputToHistory("Jihadist draws one card.", False)
            target = random.choice(possibles)
        app.removeCell(target)
        app.removeCell(target)
        prestigeRolls = []
        for i in range(3):
          prestigeRolls.append(random.randint(1,6))
        presMultiplier = 1
        if prestigeRolls[0] <= 4:
          presMultiplier = -1
        app.changePrestige(min(prestigeRolls[1], prestigeRolls[2]) * presMultiplier)
      elif self.number == 110: # Zarqawi
        if side == "US":
          app.changePrestige(3)
          app.outputToHistory("Remove card from game.", False)
        else:
          possibles = []
          for country in ["Iraq", "Syria", "Lebanon", "Jordan"]:
            if app.map[country].troops() > 0:
              possibles.append(country)
          target = random.choice(possibles)
          app.placeCells(target, 3)
          app.map[target].plots += 1
          app.outputToHistory("Add a Plot 2 to %s." % target, False)
          app.outputToHistory(app.board.country_summary(target), True)
      elif self.number == 111: # Zawahiri
        if side == "US":
          app.changeFunding(-2)
        else:
          if app.numIslamicRule() > 0:
            app.changePrestige(-3)
          else:
            app.changePrestige(-1)
      elif self.number == 112: # Bin Ladin
        if side == "US":
          app.changeFunding(-4)
          app.changePrestige(1)
          app.outputToHistory("Remove card from game.", False)
        else:
          if app.numIslamicRule() > 0:
            app.changePrestige(-4)
          else:
            app.changePrestige(-2)
      elif self.number == 113: # Darfur
        app.testCountry("Sudan")
        if app.prestige >= 7:
          app.map["Sudan"].aid = 1
          app.outputToHistory("Aid added to Sudan.", False)
          if app.map["Sudan"].alignment == "Adversary":
            app.map["Sudan"].alignment = "Neutral"
            app.outputToHistory("Sudan alignment improved.", False)
          elif app.map["Sudan"].alignment == "Neutral":
            app.map["Sudan"].alignment = "Ally"
            app.outputToHistory("Sudan alignment improved.", False)
        else:
          app.map["Sudan"].besieged = 1
          app.outputToHistory("Sudan now Besieged Regime.", False)
          if app.map["Sudan"].ally_Q():
            app.map["Sudan"].alignment = "Neutral"
            app.outputToHistory("Sudan alignment worssened.", False)
          elif app.map["Sudan"].alignment == "Neutral":
            app.map["Sudan"].alignment = "Adversary"
            app.outputToHistory("Sudan alignment worssened.", False)
        app.outputToHistory(app.board.country_summary("Sudan"), True)
      elif self.number == 114: # GTMO
        app.lapsing.append("GTMO")
        app.outputToHistory("GTMO in play. No recruit operations or Detainee Release the rest of this turn.", False)
        prestigeRolls = []
        for i in range(3):
          prestigeRolls.append(random.randint(1,6))
        presMultiplier = 1
        if prestigeRolls[0] <= 4:
          presMultiplier = -1
        app.changePrestige(min(prestigeRolls[1], prestigeRolls[2]) * presMultiplier)
      elif self.number == 115: # Hambali
        if side == "US":
          possibles = ["Indonesia/Malaysia"]
          targets = []
          target = None
          for countryObj in app.map["Indonesia/Malaysia"].links:
            possibles.append(countryObj.name)
          for country in possibles:
            if app.map[country].totalCells(True) > 0:
              if app.map[country].non_muslim_Q():
                if app.map[country].hard_Q():
                  targets.append(country)
              else:
                if app.map[country].ally_Q():
                  targets.append(country)
          if len(targets) == 1:
            target = targets[0]
          else:
            while not target:
              input = app.getCountryFromUser("Choose Indonesia or an adjacent country that has a cell and is Ally or Hard. (? for list)?: ",  "XXX", app.listHambali)
              if input == "":
                print("")
              else:
                if input not in targets:
                  print("%s is not Indonesia or an adjacent country that has a cell and is Ally or Hard." % input)
                  print("")
                else:
                  target = input
          app.removeCell(target)
          app.outputToHistory("US draw 2 cards.", False)
        else:
          possibles = ["Indonesia/Malaysia"]
          targets = []
          target = None
          for countryObj in app.map["Indonesia/Malaysia"].links:
            possibles.append(countryObj.name)
          for country in possibles:
            if app.map[country].totalCells(True) > 0:
              if app.map[country].non_muslim_Q():
                if app.map[country].hard_Q():
                  targets.append(country)
              else:
                if app.map[country].ally_Q():
                  targets.append(country)
          target = random.choice(targets)
          app.map[target].plots += 1
          app.outputToHistory("Place an plot in %s." % target, True)
      elif self.number == 116: # KSM
        if side == "US":
          for country in app.map:
            if app.map[country].plots > 0:
              if app.map[country].ally_Q() or app.map[country].non_muslim_Q():
                numPlots = app.map[country].plots
                app.map[country].plots = 0
                app.outputToHistory("%d Plots removed from %s." % (numPlots, country), False)
          app.outputToHistory("US draws 2 cards.", True)
        else:
          if app.executePlot(1, False, [1], False, False, True) == 1:
            app.outputToHistory("No plots could be placed.", True)
      elif self.number == 117 or self.number == 118: # Oil Price Spike
        app.lapsing.append("Oil Price Spike")
        app.outputToHistory("Oil Price Spike in play. Add +1 to the resources of each Oil Exporter country for the turn.", False)
        if side == "US":
          app.outputToHistory("Select, reveal, and draw a card other than Oil Price Spike from the discard pile or a box.", True)
        else:
          if app.getYesNoFromUser("Are there any Jihadist event cards in the discard pile? "):
            app.outputToHistory("Draw from the Discard Pile randomly among the highest-value Jihadist-associated event cards. Put the card on top of the Jihadist hand.", True)
      elif self.number == 119: # Saleh
        app.testCountry("Yemen")
        if side == "US":
          if app.map["Yemen"].governance != 4:
            if app.map["Yemen"].alignment == "Adversary":
              app.map["Yemen"].alignment = "Neutral"
            elif app.map["Yemen"].alignment == "Neutral":
              app.map["Yemen"].alignment = "Ally"
            app.outputToHistory("Yemen Alignment improved to %s." % app.map["Yemen"].alignment, False)
            app.map["Yemen"].aid = 1
            app.outputToHistory("Aid added to Yemen.", True)
        else:
          if app.map["Yemen"].ally_Q():
            app.map["Yemen"].alignment = "Neutral"
          elif app.map["Yemen"].alignment == "Neutral":
            app.map["Yemen"].alignment = "Adversary"
          app.outputToHistory("Yemen Alignment worssened to %s." % app.map["Yemen"].alignment, False)
          app.map["Yemen"].besieged = 1
          app.outputToHistory("Yemen now Besieged Regime.", True)
      elif self.number == 120: # US Election
        app.executeCardUSElection(random.randint(1,6))
    if self.remove:
      app.outputToHistory("Remove card from game.", True)
    if self.mark:
      app.outputToHistory("Place marker for card.", True)
    if self.lapsing:
      app.outputToHistory("Place card in Lapsing.", True)

class TroopTrack():
  def __init__(self, num) :
    self.__troops = num
    self.__troops_max = num

  def get_troops(self) : return self.__troops

  def inc_troops(self, amt) :
    t = self.get_troops() + amt
    if t > self.__troops_max : return self.add_troops(self.__troops_max - self.get_troops())
    return self.add_troops(amt)

  def dec_troops(self, amt) :
    t = self.get_troops() - amt
    if t < 0 : return self.remove_troops(self.get_troops())
    return self.remove_troops(amt)

  def remove_troops(self, num) :
    if num <= self.__troops :
      self.__troops -= num 
      return num
    else: raise Exception("Not enough available troops!")

  def add_troops(self, num) :
    if self.__troops + num <= self.__troops_max :
      self.__troops += num 
      return num
    else: raise Exception("Over MAX TROOPS!")

  def draw_amount(self) :
    for r, (d,s) in CONFLICT_STATUS.items() :
      if self.__troops in r :
        return d
    raise Exception("Unknown card draw amount!")

  def conflict_status(self) :
    for r, (d,s) in CONFLICT_STATUS.items() :
      if self.__troops in r :
        return s 

class FundingTrack():
  def __init__(self, funding, cells) :
    self.__funding = funding
    self.__cells = cells
    self.__cells_max = cells

  def funding(self): return self.__funding
  def set_funding(self, num) :
    if num in range(1, 10) : 
      self.__funding = num
      return self.funding()

    raise Exception("Funding value out of range!")

  def inc_funding(self, amt=1) :
    f = self.funding() + amt
    if f > 10 : return self.set_funding(10)
    return self.set_funding(f)

  def dec_funding(self, amt=1) :
    f = self.funding() - amt
    if f < 1 : return self.set_funding(1)
    return self.set_funding(f)

  def available_cells(self) :
    return self.__cells

  def eligible_cells(self) :
    f_section = (self.__funding - 1) // 3 + 1

     # print("funding: %d" % self.__funding)
     # print("f_section: %d" % f_section)
     # print("cells: %d" % self.__cells)
    for c in range(0, self.__cells_max + 1) :
    #  print("c: %d, e: %d\n" % (c, (self.__cells_max - self.__cells + c) // 5 + 1))
      if (self.__cells_max - self.__cells + c) // 5 + 1 > f_section :
        return c

  def remove_cells(self, num) :
    if num <= self.__cells  :
      self.__cells  -= num 
      return num
    else: raise Exception("Not enough available cells!")

  def add_cells(self, num) :
    if self.__cells  + num <= self.__cells_max :
      self.__cells  += num 
      return num
    else: raise Exception("Over MAX cells!")

  def draw_amount(self) :
    for r, d in FUNDING_STATUS.items() :
      if self.__funding in r :
        return d[0]
    raise Exception("Unknown card draw amount!")

  def funding_status(self) :
    for r, d in FUNDING_STATUS.items() :
      if self.__funding in r :
        return d[1]

class PrestigeTrack():
  def __init__(self, prestige):
    self.__prestige = prestige

  def set_prestige(self, num):
    for r, d in PRESTIGE_STATUS.items() : 
      if num in r :
        self.__prestige = num
        return num
    raise Exception("Out of bounds prestige!")

  def get_prestige(self): return self.__prestige

  def dec_prestige(self, amt = 1) :
    p = self.get_prestige() - amt
    if p <= 0 : p = 1
    return self.set_prestige(p)

  def inc_prestige(self, amt = 1) :
    p = self.get_prestige() + amt
    if p >= 13 : p = 12
    return self.set_prestige(p)

  def get_prestige_modifier(self):
    for r, d in PRESTIGE_STATUS.items() :
      if self.__prestige in r :
        return PRESTIGE_STATUS[r]
    raise Exception("Out of bounds prestige!")

 
class Board():
  def __init__(self, scenario, world_config, theapp) :
    self.troop_track = TroopTrack(TROOPS_MAX)
    self.funding_track = FundingTrack(scenario['funding'], CELLS_MAX)
    self.prestige_track = PrestigeTrack(0)
    self.__events = []
    self.__lapsing_events = []
    self.deck = {}
    self.gwot_relations = { }
    self.app = theapp
    self.world = self.world_setup(world_config)

  def country(self, country) :
    if country not in self.world.keys() : raise UnknownCountry(country)
    return self.world[country]

  def clear_lapsing_events(self) : self.__lapsing_events = []
  def lapsing_events(self) : return list(self.__lapsing_events)
  def events(self) : return list(self.__events)

  def event_in_play_Q(self, name) : return name in self.__events

  def __set_governance__(self, country, level) :
    if type(level).__name__ != 'Governance' :
      raise Exception("Not a governance level!")

    self.world[country].governance = level
    return level

  def __set_posture__(self, country, value) :
    if type(value).__name__ != 'Posture' :
      raise Exception("Not a posture value!")

    self.world[country].posture = value
    return value

  def __set_alignment__(self, country, level) :
    if type(level).__name__ != 'Alignment' :
      raise Exception("Not a alignment level!")

    self.world[country].alignment = level
    return level

  def test_country(self ,country, f = None, *args):
    if country in self.world.keys() :
      if self.world[country].test_governance_Q() :
        if random_roll() <= GOVERNANCE_DIVIDE : self.__set_governance__(country, Governance.POOR)
        else : self.__set_governance__(country, Governance.FAIR)

      if self.world[country].test_posture_Q() and self.world[country].non_muslim_Q() :
        if random_roll() <= POSTURE_DIVIDE : self.__set_posture__(country, Posture.SOFT)
        else: self.__set_posture__(country, Posture.HARD)

      if self.world[country].test_alignment_Q() :
        self.__set_alignment__(country, Alignment.NEUTRAL)

      return f(country, *args)

    else : raise UnknownCountry(country)
    
  def cadre_Q(self, country) :
    def f(country) :
      return self.world[country].cadre_Q()

    return self.test_country(country, f)

  def add_cadre(self, country) :
    def f(country) :
      self.world[country].add_cadre()

    self.test_country(country, f)
    
  def remove_cadre(self, country) :
    def f(country) :
      self.world[country].remove_cadre()

    self.test_country(country, f)

  def activate_sleepers(self, country, num = 1000) :
    s = min(num, self.world[country].sleeper_cells)
    self.world[country].sleeper_cells -= s
    self.world[country].active_cells += s
    return s

  def place_cells(self, country, num, active = False):
    def f(country, num) :
      n = min(self.funding_track.available_cells(), num)
      if active :
        self.world[country].active_cells = self.funding_track.remove_cells(n)
      elif not active :
        self.world[country].sleeper_cells = self.funding_track.remove_cells(n)
      self.world[country].remove_cadre()
      return (country, num)

    self.test_country(country, f, num)

  def place_troops(self, dst, num, src = 'troop_track'):
    def f(dst, num, src = 'troop_track') :
      if src == 'troop_track' and dst != 'troop_track' :
        self.world[dst].troops_stationed += self.troop_track.remove_troops(num)
        return (dst, num)
      elif src != 'troop_track' and dst == 'troop_track' :
        t = min(self.world[src].troops_stationed, num)
        self.troop_track.add_troops(t)
        self.world[src].troops_stationed -= t
        return (dst, t)
      elif src != 'troop_track' and dst != 'troop_track' :
        t = min(self.world[src].troops_stationed, num)
        self.world[dst].troops_stationed += t
        self.world[src].troops_stationed -= t
        return (dst, t)
       
      return (dst, num)

    if dst != 'troop_track' :
      return self.test_country(dst, f, num, src)
    else : 
      return f(dst, num, src)

  def get_schengen(self) : return [ n for n,c in self.world.items() if c.schengen ]

  def world_setup(self, world_config) :
    world = {}
    schengen = []
    for country, stats in world_config.items() :
      world[country] = Country(self.app, country, stats)
      if stats['schengen'] : schengen.append(world[country])

    for country in world_config.keys() :
      for adj in world_config[country]['adjacent_countries'] :
        if adj == 'Schengen' :
          world[country].schengenLink = True
          world[country].adjacent_countries.extend(schengen)
        else :
          world[country].adjacent_countries.append(world[adj])
      world[country].links = world[country].adjacent_countries
    return world

  def set_prestige(self, num) : self.prestige_track.set_prestige(num)

  def set_event_in_play(self, events) :
    if type(events).__name__ == 'list' :
      self.__events.extend(events)
    else: self.__events.append(events)

  def unset_event_in_play(self, events) :
    if type(events).__name__ == 'list' :
      for x in events :
        self.__events.remove(x)
    else: self.__events.remove(events)

  def add_plots(self, country, num) :
    def f(country, num) :
      self.world[country].plots += num
      return self.world[country].plots

    return self.test_country(country, f, num)

  def remove_plots(self, country, num) :
    def f(country, num) :
      p = self.world[country].plots - num
      p = max(p, 0)
      return self.world[country].plots

    return self.test_country(country, f, num)

  def set_country_event_in_play(self, country, events) :
    def f(country, events) :
      if type(events).__name__ == 'list' :
        self.world[country].markers.extend(events)
        if 'besieged' in events :
          self.world[country].besieged += 1
        if 'regime_change' in events :
          self.world[country].regime_change += 1
          
      else:
        self.world[country].markers.append(events)
        if 'besieged' == events :
          self.world[country].besieged += 1
        if 'regime_change' in events :
          self.world[country].regime_change += 1
 
    self.test_country(country, f, events)

  def unset_country_event_in_play(self, country, events) :
    def f(country, events) :
      if type(events).__name__ == 'list' :
        for x in events :
          self.world[country].markers.remove(x)
        if 'besieged' in events :
          self.world[country].besieged -= 1
        if 'regime_change' in events :
          self.world[country].regime_change -= 1
          
      else:
        self.world[country].markers.remove(events)
        if 'besieged' == events :
          self.world[country].besieged -= 1
        if 'regime_change' in events :
          self.world[country].regime_change -= 1
 
    self.test_country(country, f, events)

  def set_governance(self, country, level) :
    def f(country, level) :
      if type(level).__name__ != 'Governance' :
        raise Exception("Not a governance level!")

      self.world[country].governance = level
      return level

    self.test_country(country, f, level)

  def set_alignment(self, country, level) :
    def f(country, level) :
      if type(level).__name__ != 'Alignment' :
        raise Exception("Not a alignment level!")

      self.world[country].alignment = level
      return level

    return self.test_country(country, f, level)

  def set_posture(self, country, value) :
    def f(country, value) :
      if type(value).__name__ != 'Posture' :
        value = Posture[value]

      self.world[country].posture = value
      return value

    return self.test_country(country, f, value)

  def get_regime_change(self) :
    l = []
    for n,c in self.world.items() :
      if c.regime_change_Q() : l.append(c)

    return l

  def get_allied_countries(self) :
    l = []
    for n,c in self.world.items() :
      if c.ally_Q() : l.append(c)
      elif n == "Philippines" and "Abu Sayyaf" in c.markers : l.append(c)
    return l

  def get_troops_countries(self) :
    l = []
    for n,c in self.world.items() :
      if c.troops() > 0 : l.append(c)
    return l

  def gwot(self):
    p = 0
    world = ''
    postures = { Posture.LOCKED_HARD: 1, Posture.HARD: 1, Posture.SOFT: -1 }

    for n, c in self.world.items():
      if n != 'United States' : p += postures.get(c.posture, 0)

    if p > 0 : world = 'Hard'
    else : world = 'Soft'

    mod = min(abs(p),3)
    if world != self.world['United States'].posture.value : 
      return dict(world= world, num= mod, penalty= 0-mod)
    else : 
      return dict(world= world, num= mod, penalty = 0)

  def victory_track(self):
    vt = {
        'good_resources' : 0
      , 'islamist_resources' : 0
      , 'good_fair_countries' : 0
      , 'poor_islamist_countries' : 0
      , 'good' : []
      , 'poor' : []
      , 'fair' : []
      , 'islamist' : []
      , 'plots': []
      , 'hard' : []
      , 'soft' : [] }

    for name, c in self.world.items() :
      if c.plot_Q() : vt['plots'].append(name)
      if c.suni_Q() or c.shia_mix_Q() :
        if c.good_Q() :
          vt['good_fair_countries'] += 1
          vt['good_resources'] += c.resources
          vt['good'].append(c.get_stats())
        elif c.islamist_rule_Q() :
          vt['poor_islamist_countries'] += 1
          vt['islamist_resources'] += c.resources
          vt['islamist'].append(c.get_stats())

        if c.fair_Q() :
          vt['good_fair_countries'] += 1
          vt['fair'].append(c.get_stats())
        elif c.poor_Q() :
          vt['poor_islamist_countries'] += 1
          vt['poor'].append(c.get_stats())
      elif c.non_muslim_Q() and not c.iran_Q() :
        if c.hard_Q() : vt['hard'].append(c.get_stats())
        if c.soft_Q() : vt['soft'].append(c.get_stats())
    return vt

  def country_summary(self, cname) :
    out = ''
    temp = ''
    heading = ''

    country = self.world[cname]
    if country.non_muslim_Q() :
      temp += "   {name:<15} {resources:<5} {posture:<10} {governance:<13} {plots:^5}  [{active_cells:^5}|{sleeper_cells:^4}]  [{troops_stationed:^4}]  {cadre:*<5}\n"

      heading = "   {name:<15} {resources:<5} {posture:<10} {governance:<13} {plots:^5}  {active_cells:^6}|{sleeper_cells:^5}  {troops_stationed:^4}\n".format(name="NAME", resources= "RES", posture="POSTURE", plots="PLOTS", governance="GOV", active_cells="ACTIVE", sleeper_cells="SLEEP", troops_stationed="TROOPS")

    elif not country.iran_Q() :
      heading = "   {name:<15} {resources:<5} {align:<10} {governance:<13} {plots:^5} [{active_cells:^6}|{sleeper_cells:^5}] {troops_stationed:^4}\n".format(name="NAME", resources= "RES", align="ALIGN", plots="PLOTS", governance="GOV", active_cells="active", sleeper_cells="sleep", troops_stationed='TROOPS')

      temp += "   {name:<15} {resources:<5} {alignment:<10} {governance:<13} {plots:^5}  [{active_cells:^5}|{sleeper_cells:^4}]  [{troops_stationed:^4}]  {cadre:*<5} {aid:*<3} {besieged:*<8} {regime_change:*<12}\n"

    
    c = country.get_stats()
    if country.cadre_Q() : c['cadre'] = 'Cadre'
    else :  c['cadre'] = ''
    if country.aid_Q() : c['aid'] = 'Aid'
    else :  c['aid'] = ''
    if country.besieged_Q() : c['besieged'] = 'Besieged'
    else :  c['besieged'] = ''
    if country.regime_change_Q() : c['regime_change'] = 'Regime Change'
    else :  c['regime_change'] = ''
    if country.non_muslim_Q() : c['resources'] = '-'

    out += temp.format_map(c)
    
    if out != '' : return heading + out
    return heading + "   None: {k}\n".format(k=kind.upper())

  def world_summary(self) :
    def gen_c_str(kind) :
      out = ''
      temp = ''
      heading = ''

      if kind == 'hard' or kind == 'soft' :
        temp += "   {name:<15} {resources:<5} {posture:<10} {governance:<13} {plots:^5}  [{active_cells:^5}|{sleeper_cells:^4}]  [{troops_stationed:^4}]  {cadre:*<5}\n"
      else : 
        temp += "   {name:<15} {resources:<5} {alignment:<10} {governance:<13} {plots:^5}  [{active_cells:^5}|{sleeper_cells:^4}]  [{troops_stationed:^4}]  {cadre:*<5} {aid:*<3} {besieged:*<8} {regime_change:*<12}\n"

      
      for c in vt[kind] :
        if c['c'].cadre_Q() : c['cadre'] = 'Cadre'
        else :  c['cadre'] = ''
        if c['c'].aid_Q() : c['aid'] = 'Aid'
        else :  c['aid'] = ''
        if c['c'].besieged_Q() : c['besieged'] = 'Besieged'
        else :  c['besieged'] = ''
        if c['c'].regime_change_Q() : c['regime_change'] = 'Regime Change'
        else :  c['regime_change'] = ''
        if c['c'].non_muslim_Q() : c['resources'] = '-'

        out += temp.format_map(c)
      
      if out != '' : return heading + out
      return heading + "   None: {k}\n".format(k=kind.upper())

    vt = self.victory_track()


    out = "   {name:<15} {resources:<5} {align:<10} {governance:<13} {plots:^5} [{active_cells:^6}|{sleeper_cells:^5}] {troops_stationed:^4}\n".format(name="NAME", resources= "RES", align="ALIGN", plots="PLOTS", governance="GOV", active_cells="active", sleeper_cells="sleep", troops_stationed='TROOPS')

    out += gen_c_str('good') + "\n"

    out += gen_c_str('fair') + "\n"

    out += gen_c_str('poor') + "\n"

    out += gen_c_str('islamist') + "\n"

    out += "   {name:<15} {resources:<5} {posture:<10} {governance:<13} {plots:^5}  {active_cells:^6}|{sleeper_cells:^5}  {troops_stationed:^4}\n".format(name="NAME", resources= "RES", posture="POSTURE", plots="PLOTS", governance="GOV", active_cells="ACTIVE", sleeper_cells="SLEEP", troops_stationed="TROOPS")

    out += gen_c_str('hard') + "\n"

    out += gen_c_str('soft') + "\n"
    return out

  def tracker_summary(self) :
    vt = self.victory_track()

    out = "   Plots: {plots}\n\n".format(plots=vt['plots'])
    out += "   Events: {events}\n\n".format(events=self.events()+self.lapsing_events())

    out += "   Resources: GOOD  ISLAMIST   GOOD/FAIR   POOR/ISLAMIST\n"
    out += "              {good:^4}  {islamist:^8}   {good_fair:^9}   {poor_islamist:^13}\n\n".format(good=vt['good_resources'], islamist=vt['islamist_resources'], poor_islamist=vt['poor_islamist_countries'], good_fair=vt['good_fair_countries'])

    gwot = self.gwot()

    out += "   GWOT: WORLD  UNITED STATES   PRESTIGE\n"
    out += "   {mod:^5} {world:^5}   {united_states:^13}   {prestige:^8}\n\n".format(world=gwot['world'], mod=gwot['num'], united_states=self.world["United States"].posture, prestige=self.prestige_track.get_prestige())

    out += "   {c_status:<13} [{troops}] troops   {f_status}({funding}) [{cells}/{a_cells}] cells\n\n".format(c_status=self.troop_track.conflict_status(), troops=self.troop_track.get_troops(), f_status=self.funding_track.funding_status(), cells=self.funding_track.eligible_cells(), a_cells=self.funding_track.available_cells(), funding=self.funding_track.funding())
    return out

  def __str__(self) :
    out = self.world_summary() + self.tracker_summary()
    return out
 

class Labyrinth(cmd.Cmd):

  map = {}
  undo = False
  rollturn = -1

  scenario = 0
  ideology = 0
  prestige = 0
  troops = 0
  cells = 0
  funding = 0
  startYear = 0
  turn = 0
  uCard = 0
  jCard = 0
  phase = ""
  markers = []
  lapsing = []
  history = []
  deck = {}
  gameOver = False
  backlashInPlay = False
  testUserInput = []

  def __init__(self, theScenario, theIdeology, setupFuntion = None, testUserInput = []):
    cmd.Cmd.__init__(self)
    self.scenario = theScenario

    world_config = ''
    scenario_config = ''

    with open(SCENARIOS_FILE, 'r') as f:
      scenario_config = yaml.load(f)

    with open(MAP_FILE, 'r') as f :
      world_config = yaml.load(f)

    scenario_config = scenario_config[self.scenario]


    self.board = Board(scenario_config, world_config, self)
    self.map = self.board.world
    self.markers = self.board.events
    self.lapsing = self.board.lapsing_events
    self.ideology = theIdeology
    self.cells = 0
    self.funding = 0
    self.startYear = 0
    self.turn = 1
    self.uCard = 1
    self.jCard = 1
    self.phase = ""
    self.history = []
    self.testUserInput = testUserInput

    if setupFuntion:
      setupFuntion(self)
    else:
      self.scenario_setup()
    self.gameOver = False
    self.backlashInPlay = False

    self.deck = {}
    self.deckSetup()

  def postcmd(self, stop, line):

    self.Save(SUSPEND_FILE)

    if line == "quit":
      return True

    if self.undo:
      return True

    if self.rollturn >= 0:
      return True



  # Cells test
    cellCount = 0
    for country in self.map:
      cellCount += self.map[country].sleeper_cells
      cellCount += self.map[country].activeCells
    cellCount += self.cells
    if cellCount != 15:
      print("DEBUG: CELL COUNT %d" % cellCount)
  # Troops test
    troopCount = 0
    for country in self.map:
      troopCount += self.map[country].troops()
    troopCount += self.board.troop_track.get_troops()
    if troopCount != 15:
      print("DEBUG: TROOP COUNT %d" % troopCount)
  # Countries tested test
    for country in self.map:
      badCountry = False
      if (self.map[country].sleeper_cells > 0) or (self.map[country].active_cells > 0) or (self.map[country].troops_stationed > 0) or (self.map[country].aid > 0) or  (self.map[country].regime_change > 0) or (self.board.cadre_Q(country)) or (self.map[country].plots > 0):
        if (self.map[country].governance == 0):
          badCountry = True
        if self.map[country].non_muslim_Q():
          if (self.map[country].test_posture_Q()):
            badCountry = True
        elif self.map[country].culture != "Iran":
          if (self.map[country].alignment == ""):
            badCountry = True
      if badCountry:
        print("DEBUG: UNTESTED COUNTRY")
        print(self.board.country_summary(country))

  def emptyline(self):
    print("%d (Turn %s)" % (self.startYear + (self.turn - 1), self.turn))
    #print("Enter help for a list of commands.")
    print("")

  def debugprint(self, str):
    return
    print(str)

  def outputToHistory(self, output, lineFeed = True):
    print("   " + output)
    self.history.append(output)
    if lineFeed:
      print("")

  def setup_board(self, scenario):
    board_trackers = [ 'startYear' , 'turn' , 'phase' ]
    for t in board_trackers:
      setattr(self, t, scenario[t])

    self.board.set_prestige(scenario['prestige'])
    self.board.funding_track.set_funding(scenario['funding'])
    self.board.set_event_in_play(scenario['events'])

    setters = { 
      'governance': lambda country, governance: self.board.set_governance(country.replace('_',' '), Governance[governance]) 
      , 'alignment' : lambda country, alignment: self.board.set_alignment(country.replace('_',' '), Alignment[alignment])
      , 'troops_stationed': lambda country, troops: self.board.place_troops(country.replace('_',' '), troops)
      , 'sleeper_cells' : lambda country, sleeper_cells: self.board.place_cells(country.replace('_',' '), sleeper_cells)
      , 'active_cells' : lambda country, active_cells: self.board.place_cells(country.replace('_',' '), active_cells, True)
      , 'besieged': lambda country, v: self.board.set_country_event_in_play(country.replace('_',' '), 'besieged')
      , 'regime_change': lambda country, v: self.board.set_country_event_in_play(country.replace('_',' '), 'besieged')
      , 'markers': lambda country, v: self.board.set_country_event_in_play(country.replace('_',' '), 'besieged')
      , 'posture' : lambda country, posture: self.board.set_posture(country.replace('_',' '), Posture[posture])
      , 'plots' : lambda country, plots: self.board.add_plots(country,plots)
    }

    for country, state in scenario['world_state'].items():
      for k, v in state.items():
        setters[k](country,v)

    if scenario['random_cell_placement']['countries'] > 0 and scenario['random_cell_placement']['cells_per_country'] > 0:
      self.randomly_place_cells(scenario['random_cell_placement']['countries'], scenario['random_cell_placement']['cells_per_country'])

  def randomly_place_cells(self, num_countries, num_cell_per_country):
    for country in random.sample(list(self.map.keys()), num_countries):
      self.board.place_cells(country, num_cell_per_country)
    
  def test_countries(self, countries):
    for country in countries :
      self.testCountry(country) 

  def num_good_resources(self):
    return sum([ self.countryResources(n) for n, c in self.map.items() if c.governance == Governance.GOOD and (c.shia_mix_Q() or c.suni_Q())])

  def num_islamist_resources(self):
    return sum([ self.countryResources(n) for n, c in self.map.items() if c.governance == Governance.ISLAMIST_RULE and (c.shia_mix_Q() or c.suni_Q())])

  def num_good_countries(self):
    return len([ n for n, c in self.map.items() if c.governance <= Governance.FAIR and (c.shia_mix_Q() or c.suni_Q()) and c.governance != Governance.TEST ])

  def num_poor_countries(self):
    return len([ n for n, c in self.map.items() if c.governance > Governance.FAIR and (c.shia_mix_Q() or c.suni_Q()) ])

  def scenario_setup(self):
    scenarios = None
    with open(SCENARIOS_FILE, 'r') as f:
      scenarios = yaml.load(f)

    self.setup_board(scenarios[self.scenario]) 

    if self.scenario == 'lets_roll' or self.scenario == 'test_scenario':
      True
    elif self.scenario == 'you_can_call_me_al' :
      print("   REMOVE THE CARD Axis of Evil FROM THE GAME. \n")
    elif self.scenario == 'anaconda' :
      print("   REMOVE THE CARDS Patriot Act and Tora Bora FROM THE GAME. \n")
    elif self.scenario == 'mission_accomplished' :
      self.test_countries([n for n, c in self.map.items() if c.schengen])
      print("   REMOVE THE CARDS Patriot Act, Tora Bora, NEST, Abu Sayyaf, KSM and Iraqi WMD FROM THE GAME. \n")
    else : raise Exception("Unknown scenario!")

  def deckSetup(self):
    self.deck["1"] = Card(1,"US","Backlash",1,False,False,False)
    self.deck["2"] = Card(2,"US","Biometrics",1,False,False,True)
    self.deck["3"] = Card(3,"US","CTR",1,False,True,False)
    self.deck["4"] = Card(4,"US","Moro Talks",1,True,True,False)
    self.deck["5"] = Card(5,"US","NEST",1,True,True,False)
    self.deck["6"] = Card(6,"US","Sacntions",1,False,False,False)
    self.deck["7"] = Card(7,"US","Sanctions",1,False,False,False)
    self.deck["8"] = Card(8,"US","Special Forces",1,False,False,False)
    self.deck["9"] = Card(9,"US","Special Forces",1,False,False,False)
    self.deck["10"] = Card(10,"US","Special Forces",1,False,False,False)
    self.deck["11"] = Card(11,"US","Abbas",2,True,True,False)
    self.deck["12"] = Card(12,"US","Al-Azhar",2,False,False,False)
    self.deck["13"] = Card(13,"US","Anbar Awakening",2,False,True,False)
    self.deck["14"] = Card(14,"US","Covert Action",2,False,False,False)
    self.deck["15"] = Card(15,"US","Ethiopia Strikes",2,True,False,False)
    self.deck["16"] = Card(16,"US","Euro-Islam",2,True,False,False)
    self.deck["17"] = Card(17,"US","FSB",2,False,False,False)
    self.deck["18"] = Card(18,"US","Intel Community",2,False,False,False)
    self.deck["19"] = Card(19,"US","Kemalist Republic",2,False,False,False)
    self.deck["20"] = Card(20,"US","King Abdullah",2,True,False,False)
    self.deck["21"] = Card(21,"US","Let's Roll",2,False,False,False)
    self.deck["22"] = Card(22,"US","Mossad and Shin Bet",2,False,False,False)
    self.deck["23"] = Card(23,"US","Predator",2,False,False,False)
    self.deck["24"] = Card(24,"US","Predator",2,False,False,False)
    self.deck["25"] = Card(25,"US","Predator",2,False,False,False)
    self.deck["26"] = Card(26,"US","Quartet",2,False,False,False)
    self.deck["27"] = Card(27,"US","Sadam Captured",2,True,True,False)
    self.deck["28"] = Card(28,"US","Sharia",2,False,False,False)
    self.deck["29"] = Card(29,"US","Tony Blair",2,True,False,False)
    self.deck["30"] = Card(30,"US","UN Nation Building",2,False,False,False)
    self.deck["31"] = Card(31,"US","Wiretapping",2,False,True,False)
    self.deck["32"] = Card(32,"US","Back Channel",3,False,False,False)
    self.deck["33"] = Card(33,"US","Benazir Bhutto",3,True,True,False)
    self.deck["34"] = Card(34,"US","Enhanced Measures",3,False,True,False)
    self.deck["35"] = Card(35,"US","Hijab",3,True,False,False)
    self.deck["36"] = Card(36,"US","Indo-Pakistani Talks",3,True,True,False)
    self.deck["37"] = Card(37,"US","Iraqi WMD",3,True,True,False)
    self.deck["38"] = Card(38,"US","Libyan Deal",3,True,True,False)
    self.deck["39"] = Card(39,"US","Libyan WMD",3,True,True,False)
    self.deck["40"] = Card(40,"US","Mass Turnout",3,False,False,False)
    self.deck["41"] = Card(41,"US","NATO",3,False,True,False)
    self.deck["42"] = Card(42,"US","Pakistani Offensive",3,False,False,False)
    self.deck["43"] = Card(43,"US","Patriot Act",3,True,True,False)
    self.deck["44"] = Card(44,"US","Renditions",3,False,True,False)
    self.deck["45"] = Card(45,"US","Safer Now",3,False,False,False)
    self.deck["46"] = Card(46,"US","Sistani",3,False,False,False)
    self.deck["47"] = Card(47,"US","The door of Itjihad was closed",3,False,False,True)
    self.deck["48"] = Card(48,"Jihadist","Adam Gadahn",1,False,False,False)
    self.deck["49"] = Card(49,"Jihadist","Al-Ittihad al-Islami",1,True,False,False)
    self.deck["50"] = Card(50,"Jihadist","Ansar al-Islam",1,True,False,False)
    self.deck["51"] = Card(51,"Jihadist","FREs",1,False,False,False)
    self.deck["52"] = Card(52,"Jihadist","IEDs",1,False,False,False)
    self.deck["53"] = Card(53,"Jihadist","Madrassas",1,False,False,False)
    self.deck["54"] = Card(54,"Jihadist","Moqtada al-Sadr",1,True,True,False)
    self.deck["55"] = Card(55,"Jihadist","Uyghur Jihad",1,True,False,False)
    self.deck["56"] = Card(56,"Jihadist","Vieira de Mello Slain",1,True,True,False)
    self.deck["57"] = Card(57,"Jihadist","Abu Sayyaf",2,True,True,False)
    self.deck["58"] = Card(58,"Jihadist","Al-Anbar",2,True,True,False)
    self.deck["59"] = Card(59,"Jihadist","Amerithrax",2,False,False,False)
    self.deck["60"] = Card(60,"Jihadist","Bhutto Shot",2,True,True,False)
    self.deck["61"] = Card(61,"Jihadist","Detainee Release",2,False,False,False)
    self.deck["62"] = Card(62,"Jihadist","Ex-KGB",2,False,False,False)
    self.deck["63"] = Card(63,"Jihadist","Gaza War",2,False,False,False)
    self.deck["64"] = Card(64,"Jihadist","Hariri Killed",2,True,False,False)
    self.deck["65"] = Card(65,"Jihadist","HEU",2,True,False,False)
    self.deck["66"] = Card(66,"Jihadist","Homegrown",2,False,False,False)
    self.deck["67"] = Card(67,"Jihadist","Islamic Jihad Union",2,True,False,False)
    self.deck["68"] = Card(68,"Jihadist","Jemaah Islamiya",2,False,False,False)
    self.deck["69"] = Card(69,"Jihadist","Kazakh Strain",2,True,False,False)
    self.deck["70"] = Card(70,"Jihadist","Lashkar-e-Tayyiba",2,False,False,False)
    self.deck["71"] = Card(71,"Jihadist","Loose Nuke",2,True,False,False)
    self.deck["72"] = Card(72,"Jihadist","Opium",2,False,False,False)
    self.deck["73"] = Card(73,"Jihadist","Pirates",2,True,True,False)
    self.deck["74"] = Card(74,"Jihadist","Schengen Visas",2,False,False,False)
    self.deck["75"] = Card(75,"Jihadist","Schroeder & Chirac",2,False,False,False)
    self.deck["76"] = Card(76,"Jihadist","Abu Ghurayb",3,True,False,False)
    self.deck["77"] = Card(77,"Jihadist","Al Jazeera",3,False,False,False)
    self.deck["78"] = Card(78,"Jihadist","Axis of Evil",3,False,False,False)
    self.deck["79"] = Card(79,"Jihadist","Clean Operatives",3,False,False,False)
    self.deck["80"] = Card(80,"Jihadist","FATA",3,False,True,False)
    self.deck["81"] = Card(81,"Jihadist","Foreign Fighters",3,False,False,False)
    self.deck["82"] = Card(82,"Jihadist","Jihadist Videos",3,False,False,False)
    self.deck["83"] = Card(83,"Jihadist","Kashmir",3,False,False,False)
    self.deck["84"] = Card(84,"Jihadist","Leak",3,False,False,False)
    self.deck["85"] = Card(85,"Jihadist","Leak",3,False,False,False)
    self.deck["86"] = Card(86,"Jihadist","Lebanon War",3,False,False,False)
    self.deck["87"] = Card(87,"Jihadist","Martyrdom Operation",3,False,False,False)
    self.deck["88"] = Card(88,"Jihadist","Martyrdom Operation",3,False,False,False)
    self.deck["89"] = Card(89,"Jihadist","Martyrdom Operation",3,False,False,False)
    self.deck["90"] = Card(90,"Jihadist","Quagmire",3,False,False,False)
    self.deck["91"] = Card(91,"Jihadist","Regional al-Qaeda",3,False,False,False)
    self.deck["92"] = Card(92,"Jihadist","Saddam",3,False,False,False)
    self.deck["93"] = Card(93,"Jihadist","Taliban",3,False,False,False)
    self.deck["94"] = Card(94,"Jihadist","The door of Itjihad was closed",3,False,False,False)
    self.deck["95"] = Card(95,"Jihadist","Wahhabism",3,False,False,False)
    self.deck["96"] = Card(96,"Unassociated","Danish Cartoons",1,True,False,False)
    self.deck["97"] = Card(97,"Unassociated","Fatwa",1,False,False,False)
    self.deck["98"] = Card(98,"Unassociated","Gaza Withdrawal",1,True,False,False)
    self.deck["99"] = Card(99,"Unassociated","HAMAS Elected",1,True,False,False)
    self.deck["100"] = Card(100,"Unassociated","Hizb Ut-Tahrir",1,False,False,False)
    self.deck["101"] = Card(101,"Unassociated","Kosovo",1,False,False,False)
    self.deck["102"] = Card(102,"Unassociated","Former Soviet Union",2,False,False,False)
    self.deck["103"] = Card(103,"Unassociated","Hizballah",2,False,False,False)
    self.deck["104"] = Card(104,"Unassociated","Iran",2,False,False,False)
    self.deck["105"] = Card(105,"Unassociated","Iran",2,False,False,False)
    self.deck["106"] = Card(106,"Unassociated","Jaysh al-Mahdi",2,False,False,False)
    self.deck["107"] = Card(107,"Unassociated","Kurdistan",2,False,False,False)
    self.deck["108"] = Card(108,"Unassociated","Musharraf",2,False,False,False)
    self.deck["109"] = Card(109,"Unassociated","Tora Bora",2,True,False,False)
    self.deck["110"] = Card(110,"Unassociated","Zarqawi",2,False,False,False)
    self.deck["111"] = Card(111,"Unassociated","Zawahiri",2,False,False,False)
    self.deck["112"] = Card(112,"Unassociated","Bin Ladin",3,False,False,False)
    self.deck["113"] = Card(113,"Unassociated","Darfur",3,False,False,False)
    self.deck["114"] = Card(114,"Unassociated","GTMO",3,False,False,True)
    self.deck["115"] = Card(115,"Unassociated","Hambali",3,False,False,False)
    self.deck["116"] = Card(116,"Unassociated","KSM",3,False,False,False)
    self.deck["117"] = Card(117,"Unassociated","Oil Price Spike",3,False,False,True)
    self.deck["118"] = Card(118,"Unassociated","Oil Price Spike",3,False,False,True)
    self.deck["119"] = Card(119,"Unassociated","Saleh",3,False,False,False)
    self.deck["120"] = Card(120,"Unassociated","US Election",3,False,False,False)

  def my_raw_input(self, prompt):
    if len(self.testUserInput) > 0:
      retVal = self.testUserInput[0]
      self.testUserInput.remove(retVal)
      print("TEST: Prompt: %s VAL: %s" % (prompt, retVal))
      return retVal
    else:
      return raw_input(prompt)

  def getCountryFromUser(self, prompt, special, helpFunction, helpParameter = None):
    goodCountry = None
    while not goodCountry:
      input = self.my_raw_input(prompt)
      if input == "":
        return ""
      elif input == "?" and helpFunction:
        helpFunction(helpParameter)
        continue
      elif input == special:
        return special
      possible = []
      for country in self.map:
        if input.lower() == country.lower():
          possible = []
          possible.append(country)
          break
        elif input.lower() in country.lower():
          possible.append(country)
      if len(possible) == 0:
        print("Unrecognized country.")
        print("")
      elif len(possible) > 1:
        print("Be more specific", possible)
        print("")
      else:
        goodCountry = possible[0]
    return goodCountry

  def getNumTroopsFromUser(self, prompt, max):
    goodNum = None
    while not goodNum:
      try:
        input = self.my_raw_input(prompt)
        input = int(input)
        if input <= max:
          return input
        else:
          print("Not enough troops.")
          print("")
      except:
        print("Entry error")
        print("")

  def getCardNumFromUser(self, prompt):
    goodNum = None
    while not goodNum:
      try:
        input = self.my_raw_input(prompt)
        if input.lower() == "none":
          return "none"
        input = int(input)
        if input <= 120:
          return input
        else:
          print("Enter a card number.")
          print("")
      except:
        print("Enter a card number.")
        print("")

  def getPlotTypeFromUser(self, prompt):
    goodNum = None
    while not goodNum:
      try:
        input = self.my_raw_input(prompt)
        if input.lower() == "w" or input.lower() == "wmd":
          return "WMD"
        input = int(input)
        if input <= 3 and input >= 1:
          return input
        else:
          print("Enter 1, 2, 3 or W for WMD.")
          print("")
      except:
        print("Enter 1, 2, 3 or W for WMD.")
        print("")

  def getRollFromUser(self, prompt):
    goodNum = None
    while not goodNum:
      try:
        input = self.my_raw_input(prompt)
        if input == "r":
          roll = random.randint(1,6)
          print("Roll: %d" % roll)
          return roll
        input = int(input)
        if 1 <= input and input <= 6:
          return input
        else:
          raise
      except:
        print("Entry error")
        print("")

  def getYesNoFromUser(self, prompt):
    good = None
    while not good:
      try:
        input = self.my_raw_input(prompt)
        if input.lower() == "y" or input.lower() == "yes":
          return True
        elif input.lower() == "n" or input.lower() == "no":
          return False
        else:
          print("Enter y or n.")
          print("")
      except:
        print("Enter y or n.")
        print("")

  def getPostureFromUser(self, prompt):
    good = None
    while not good:
      try:
        input = self.my_raw_input(prompt)
        if input.lower() == "h" or input.lower() == "hard":
          return "Hard"
        elif input.lower() == "s" or input.lower() == "soft":
          return "Soft"
        else:
          print("Enter h or s.")
          print("")
      except:
        print("Enter h or s.")
        print("")

  def getEventOrOpsFromUser(self, prompt):
    good = None
    while not good:
      try:
        input = self.my_raw_input(prompt)
        if input.lower() == "e" or input.lower() == "event":
          return "event"
        elif input.lower() == "o" or input.lower() == "ops":
          return "ops"
        else:
          print("Enter e or o.")
          print("")
      except:
        print("Enter e or o.")
        print("")

  def modifiedWoIRoll(self, baseRoll, country, useGWOTPenalty = True):
    modRoll = baseRoll

    if self.board.prestige_track.get_prestige() <= 3:
      modRoll -= 1
      self.outputToHistory("-1 for Prestige", False)
    elif self.board.prestige_track.get_prestige() >= 7 and self.board.prestige_track.get_prestige() <=9:
      modRoll += 1
      self.outputToHistory("+1 for Prestige", False)
    elif self.board.prestige_track.get_prestige() >= 10:
      modRoll += 2
      self.outputToHistory("+2 for Prestige", False)

    if self.map[country].ally_Q() and self.map[country].fair_Q():
      modRoll -= 1
      self.outputToHistory("-1 for Attempt to shift to Good", False)

    if useGWOTPenalty:
      modRoll += self.board.gwot()['penalty']
      if self.board.gwot()['penalty'] != 0:
        self.outputToHistory("-1 for GWOT Relations Penalty", False)

    if self.map[country].aid_Q() :
      modRoll += 1
      self.outputToHistory("+1 for Aid", False)

    for adj in self.map[country].links:
      if adj.ally_Q() and adj.good_Q():
        modRoll += 1
        self.outputToHistory("+1 for Adjacent Good Ally", False)
        break
    return modRoll

  def changePrestige(self, delta, lineFeed = True):
    self.board.prestige_track.inc_prestige(delta)
    if self.board.prestige_track.get_prestige() < 1:
      self.board.prestige_track.set_prestige(1)
    elif self.board.prestige_track.get_prestige() > 12:
      self.board.prestige_track.set_prestige(12)
    self.outputToHistory("Prestige now %d" % self.prestige, lineFeed)

  def changeFunding(self, delta, lineFeed = True):
    self.funding += delta
    if self.funding < 1:
      self.funding = 1
    elif self.funding > 9:
      self.funding = 9
    self.outputToHistory("Jihadist Funding now %d" % self.funding, lineFeed)

  def placeCells(self, country, numCells):
    if self.cells == 0:
      self.outputToHistory("No cells are on the Funding Track.", True)
    else:
      self.testCountry(country)
      cellsToMove = min(numCells, self.cells)
      self.map[country].sleeper_cells += cellsToMove
      # remove cadre
      self.board.remove_cadre(country)
      self.cells -= cellsToMove
      self.outputToHistory("%d Sleeper Cell(s) placed in %s" % (cellsToMove, country), False)
      self.outputToHistory(self.board.country_summary(country), True)

  def removeCell(self, country):
    if self.map[country].totalCells() == 0:
      return
    if "Sadr" in self.map[country].markers:
      self.map[country].markers.remove("Sadr")
      self.outputToHistory("Sadr removed from %s." % country, True)
    elif self.map[country].sleeper_cells > 0:
      self.map[country].sleeper_cells -= 1
      self.cells += 1
      self.outputToHistory("Sleeper Cell removed from %s." % country, True)
    else:
      self.map[country].active_cells -= 1
      self.cells += 1
      self.outputToHistory("Active Cell removed from %s." % country, True)
    if self.map[country].totalCells() == 0:
      self.outputToHistory("Cadre added in %s." % country, True)
      self.board.add_cadre(country)

  def removeAllCellsFromCountry(self, country):
    cellsToRemove = self.map[country].totalCells()
    if self.map[country].sleeper_cells > 0:
      numCells = self.map[country].sleeper_cells
      self.map[country].sleeper_cells -= numCells
      self.cells += numCells
      self.outputToHistory("%d Sleeper Cell(s) removed from %s." % (numCells, country), False)
    if self.map[country].active_cells > 0:
      numCells = self.map[country].activeCells
      self.map[country].active_cells -= numCells
      self.cells += numCells
      self.outputToHistory("%d Active Cell(s) removed from %s." % (numCells, country), False)
    if cellsToRemove > 0:
      self.outputToHistory("Cadre added in %s." % country, False)
      self.board.add_cadre(country)

  def improveGovernance(self, country):
    self.map[country].governance -= 1
    if self.map[country].governance <= 1:
      self.map[country].governance = 1
      self.map[country].regime_change = 0
      self.map[country].aid = 0
      self.map[country].besieged = 0

  def worsenGovernance(self, country):
    self.map[country].governance += 1
    if self.map[country].governance >= 4:
      self.map[country].governance = 3

  def numCellsAvailable(self, ignoreFunding = False):

    retVal = self.cells
    if ignoreFunding:
      return retVal

    if self.funding <= 3:
      retVal -= 10
    elif self.funding <= 6:
      retVal -= 5
    return max(retVal, 0)

  def numIslamicRule(self):
    numIR = 0
    for country in self.map:
      if self.map[country].islamist_rule_Q():
        numIR += 1
    return numIR

  def numBesieged(self):
    numBesieged = 0
    for country in self.map:
      if self.map[country].besieged > 0:
        numBesieged += 1
    return numBesieged

  def numRegimeChange(self):
    numRC = 0
    for country in self.map:
      if self.map[country].regime_change > 0:
        numRC += 1
    return numRC

  def numAdversary(self):
    numAdv = 0
    for country in self.map:
      if self.map[country].alignment == "Adversary":
        numAdv += 1
    return numAdv

  def numDisruptable(self):
    numDis = 0
    for country in self.map:
      if self.map[country].totalCells(False) > 0 or self.board.cadre_Q(country):
        if self.map[country].troops() > 0 or self.map[country].non_muslim_Q() or self.map[country].ally_Q():
          numDis += 1
    return numDis

  def countryResources(self, country):
    res = self.map[country].resources
    if self.map[country].oil:
      spikes = 0
      for event in self.lapsing:
        if event == "Oil Price Spike":
          spikes += 1
      res += spikes
    return res

  def handleMuslimWoI(self, roll, country):
    if roll <= 3:
      self.outputToHistory("* WoI in %s failed." % country)
    elif roll == 4:
      self.map[country].aid = 1
      self.outputToHistory("* WoI in %s adds Aid." % country, False)
      self.outputToHistory(self.board.country_summary(country), True)
    else:
      if self.map[country].alignment == "Neutral":
        self.map[country].alignment = "Ally"
        self.outputToHistory("* WoI in %s succeeded - Alignment now Ally." % country, False)
        self.outputToHistory(self.board.country_summary(country), True)
      elif self.map[country].ally_Q():
        self.improveGovernance(country)
        self.outputToHistory("* WoI in %s succeeded - Governance now %s." % (country, self.map[country].govStr()), False)
        self.outputToHistory(self.board.country_summary(country), True)

  def handleAlert(self, country):
    if self.map[country].plots > 0:
      self.map[country].plots -= 1
      self.outputToHistory("* Alert in %s - %d plot(s) remain." % (country, self.map[country].plots))

  def handleReassessment(self):
    if self.map["United States"].hard_Q():
      self.board.set_posture("United States", Posture.SOFT)
    else:
      self.board.set_posture("United States", Posture.HARD)
    self.outputToHistory("* Reassessment = US Posture now %s" % self.map["United States"].posture)

  def handleRegimeChange(self, where, moveFrom, howMany, govRoll, prestigeRolls):
    if self.map["United States"].soft_Q(): return

    self.board.place_troops(where, howMany, moveFrom)
    self.board.activate_sleepers(where)
    self.board.set_alignment(where, Alignment.ALLY)

    if govRoll <= GOVERNANCE_DIVIDE : self.board.set_governance(where, Governance.POOR)
    else : self.board.set_governance(where, Governance.FAIR)

    self.board.set_country_event_in_play(where, 'regime_change')

    presMultiplier = 1
    if prestigeRolls[0] <= 4:
      presMultiplier = -1
    self.changePrestige(min(prestigeRolls[1], prestigeRolls[2]) * presMultiplier)
    self.outputToHistory("* Regime Change in %s" % where, False)
    self.outputToHistory(self.board.country_summary(where), False)
    if moveFrom == "troop_track":
      self.outputToHistory("%d Troops on Troop Track" % self.board.troop_track.get_troops(), False)
    else:
      self.outputToHistory("%d Troops in %s" % (self.map[moveFrom].troops(), moveFrom), False)
    self.outputToHistory("US Prestige %d" % self.board.prestige_track.get_prestige())
    if where == "Iraq" and "Iraqi WMD" in self.markers:
      self.markers.remove("Iraqi WMD")
      self.outputToHistory("Iraqi WMD no longer in play.", True)
    if where == "Libya" and "Libyan WMD" in self.markers:
      self.markers.remove("Libyan WMD")
      self.outputToHistory("Libyan WMD no longer in play.", True)

  def handleWithdraw(self, moveFrom, moveTo, howMany, prestigeRolls):
    if self.map["United States"].hard_Q():
      return
    self.map[moveFrom].changeTroops(-howMany)
    if moveTo == "track":
      self.board.troop_track.inc_troops(howMany)
    else:
      self.map[moveTo].changeTroops(howMany)
    self.map[moveFrom].aid = 0
    self.map[moveFrom].besieged = 1
    presMultiplier = 1
    if prestigeRolls[0] <= 4:
      presMultiplier = -1
    self.changePrestige(min(prestigeRolls[1], prestigeRolls[2]) * presMultiplier)
    self.outputToHistory("* Withdraw troops from %s" % moveFrom, False)
    self.outputToHistory(self.board.country_summary(moveFrom), False)
    if moveTo == "track":
      self.outputToHistory("%d Troops on Troop Track" % self.board.troop_track.get_troops(), False)
    else:
      self.outputToHistory("%d Troops in %s" % (self.map[moveTo].troops(), moveTo), False)
      self.outputToHistory(self.board.country_summary(moveTo), False)
    self.outputToHistory("US Prestige %d" % self.board.prestige_track.get_prestige())

  def handleDisrupt(self, where):
    numToDisrupt = 1
    if "Al-Anbar" in self.markers and (where == "Iraq" or where == "Syria"):
      numToDisrupt = 1
    elif self.map[where].troops() >= 2 or self.map[where].hard_Q():
      numToDisrupt = min(2, self.map[where].totalCells(False))
    if self.map[where].totalCells(False) <= 0 and self.map[where].cadre > 0:
      if "Al-Anbar" not in self.markers:
        self.outputToHistory("* Cadre removed in %s" % where)
        self.map[where].cadre = 0
    elif self.map[where].totalCells(False) <= numToDisrupt:
      self.outputToHistory("* %d cell(s) disrupted in %s." % (self.map[where].totalCells(False), where), False)
      if self.map[where].sleeper_cells > 0:
        self.map[where].active_cells += self.map[where].sleeper_cells
        numToDisrupt -= self.map[where].sleeper_cells
        self.map[where].sleeper_cells = 0
      if numToDisrupt > 0:
        self.map[where].active_cells -= numToDisrupt
        self.cells += numToDisrupt
        if self.map[where].active_cells < 0:
          self.map[where].active_cells = 0
        if self.cells > 15:
          self.cells = 15
      if self.map[where].totalCells(False) <= 0:
        self.outputToHistory("Cadre added in %s." % where, False)
        self.map[where].cadre = 1
      if self.map[where].troops() >= 2:
        self.board.prestige_track.inc_prestige(1)
        if self.board.prestige_track.get_prestige() > 12:
          self.board.prestige_track.set_prestige(12)
        self.outputToHistory("US Prestige now %d." % self.prestige, False)
      self.outputToHistory(self.board.country_summary(where), True)
    else:
      if self.map[where].active_cells == 0:
        self.map[where].active_cells += numToDisrupt
        self.map[where].sleeper_cells -= numToDisrupt
        self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where), False)
      elif self.map[where].sleeper_cells == 0:
        self.map[where].active_cells -= numToDisrupt
        self.cells += numToDisrupt
        self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where), False)
        if self.map[where].totalCells(False) <= 0:
          self.outputToHistory("Cadre added in %s." % where, False)
          self.map[where].cadre = 1
      else:
        if numToDisrupt == 1:
          disStr = None
          while not disStr:
            input = self.my_raw_input("You can disrupt one cell. Enter a or s for either an active or sleeper cell: ")
            input = input.lower()
            if input == "a" or input == "s":
              disStr = input
          if disStr == "a":
            self.map[where].active_cells -= numToDisrupt
            self.cells += numToDisrupt
            self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where))
          else:
            self.map[where].sleeper_cells -= numToDisrupt
            self.map[where].active_cells += numToDisrupt
            self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where))
        else:
          disStr = None
          while not disStr:
            if self.map[where].sleeper_cells >= 2 and self.map[where].active_cells >= 2:
              input = self.my_raw_input("You can disrupt two cells. Enter aa, as, or ss for active or sleeper cells: ")
              input = input.lower()
              if input == "aa" or input == "as" or input == "sa" or input == "ss":
                disStr = input
            elif self.map[where].sleeper_cells >= 2:
              input = self.my_raw_input("You can disrupt two cells. Enter as, or ss for active or sleeper cells: ")
              input = input.lower()
              if input == "as" or input == "sa" or input == "ss":
                disStr = input
            elif self.map[where].active_cells >= 2:
              input = self.my_raw_input("You can disrupt two cells. Enter aa, or as for active or sleeper cells: ")
              input = input.lower()
              if input == "as" or input == "sa" or input == "aa":
                disStr = input
          if input == "aa":
            self.map[where].active_cells -= 2
            self.cells += 2
            self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where))
          elif input == "as" or input == "sa":
            self.map[where].sleeper_cells -= 1
            self.cells += 1
            self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where))
          else:
            self.map[where].sleeper_cells -= 2
            self.map[where].active_cells += 2
            self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where))
      if self.map[where].troops() >= 2:
        self.board.prestige_track.inc_prestige(1)
        if self.board.prestige_track.get_prestige() > 12:
          self.board.prestige_track.set_prestige(12)
        self.outputToHistory("US Prestige now %d." % self.prestige, False)
      self.outputToHistory(self.board.country_summary(where), True)

  def executeJihad(self, country, rollList):
    successes = 0
    failures = 0
    for roll in rollList:
      if roll <= self.map[country].governance:
        successes += 1
      else:
        failures += 1
    isMajorJihad = country in self.majorJihadPossible(len(rollList))
    self.outputToHistory("Jihad operation.  %d Successes rolled, %d Failures rolled" % (successes, failures), False)
    if isMajorJihad: # all cells go active
      self.outputToHistory("* Major Jihad attempt in %s" % country, False)
      sleepers = self.map[country].sleeper_cells
      self.map[country].sleeper_cells = 0
      self.map[country].active_cells += sleepers
      self.outputToHistory("All cells go Active", False)
      if ((failures >= 2  and self.map[country].besieged == 0) or (failures == 3 and self.map[country].besieged == 1))  and (len(rollList) == 3) and self.map[country].poor_Q():
        self.outputToHistory("Major Jihad Failure", False)
        self.map[country].besieged = 1
        self.outputToHistory("Besieged Regime", False)
        if self.map[country].alignment == "Adversary":
          self.map[country].alignment = "Neutral"
        elif self.map[country].alignment == "Neutral":
          self.map[country].alignment = "Ally"
        self.outputToHistory("Alignment %s" % self.map[country].alignment, False)
    else: # a cell is active for each roll
      self.outputToHistory("* Minor Jihad attempt in %s" % country, False)
      for i in range(len(rollList) - self.map[country].numActiveCells()):
        self.outputToHistory("Cell goes Active", False)
        self.map[country].sleeper_cells -= 1
        self.map[country].active_cells += 1
    while successes > 0 and self.map[country].governance < 3:
      self.map[country].governance += 1
      successes -= 1
      self.outputToHistory("Governance to %s" % self.map[country].govStr(), False)
      self.map[country].aid = 0
    if isMajorJihad and ((successes >= 2) or ((self.map[country].besieged > 0) and (successes >= 1))) : # Major Jihad
      self.outputToHistory("Islamic Revolution in %s" % country, False)
      self.map[country].governance = 4
      self.outputToHistory("Governance to Islamic Rule", False)
      self.map[country].alignment = "Adversary"
      self.outputToHistory("Alingment to Adversary", False)
      self.map[country].regime_change = 0
      if self.map[country].besieged > 0:
        self.outputToHistory("Besieged Regime marker removed.", False)

      self.map[country].besieged = 0
      self.map[country].aid = 0
      self.funding = min(9, self.funding + self.countryResources(country))
      self.outputToHistory("Funding now %d" % self.funding, False)
      if self.map[country].troops() > 0:
        self.board.prestige_track.set_prestige(1)
        self.outputToHistory("Troops present so US Prestige now 1", False)
    if self.ideology <= 4:
      for i in range(failures):
        if self.map[country].numActiveCells() > 0:
          self.map[country].removeActiveCell()
        else:
          self.map[country].sleeper_cells -= 1
          self.outputToHistory("Sleeper cell Removed to Funding Track", False)
          self.cells += 1
    self.outputToHistory(self.board.country_summary(country), False)
    print("")

  def handleJihad(self, country, ops):
    '''Returns number of unused Ops'''
    cells = self.map[country].totalCells(True)
    rollList = []
    for i in range(min(cells, ops)):
      rollList.append(random.randint(1,6))
    self.executeJihad(country, rollList)
    return ops - len(rollList)

  def handleMinorJihad(self, countryList, ops):
    opsRemaining = ops
    for countryData in countryList:
      self.handleJihad(countryData[0], countryData[1])
      opsRemaining -= countryData[1]
    return opsRemaining

  def extraCellsNeededForMajorJihad(self):
    plusCellsNeeded = 5
    if self.ideology >= 3:
      plusCellsNeeded = 3
    return plusCellsNeeded

  def majorJihadPossible(self, ops):
    '''Return list of countries where regime change is possible.'''
    possible = []
    plusCellsNeeded = self.extraCellsNeededForMajorJihad()
    for country in self.map:
      if self.map[country].suni_Q() or self.map[country].shia_mix_Q():
        if "Benazir Bhutto" in self.markers and country == "Pakistan":
          continue
        if self.map[country].governance != 4:
          if ((self.map[country].totalCells(True)) - self.map[country].troops()) >= plusCellsNeeded:
            need = 2
            need += 3 - self.map[country].governance
            if self.map[country].besieged:
              need -= 1
            if ops >= need:
              possible.append(country)
    return possible

  def majorJihadChoice(self, ops):
    '''Return AI choice country.'''
    possible = self.majorJihadPossible(ops)
    if possible == []:
      return False
    else:
      if "Pakistan" in possible:
        return "Pakistan"
      else:
        maxResource = 0
        for country in possible:
          if self.countryResources(country) > maxResource:
            maxResource = self.countryResources(country)
        newPossible = []
        for country in possible:
          if self.countryResources(country) == maxResource:
            newPossible.append(country)
        return random.choice(newPossible)

  def minorJihadInGoodFairChoice(self, ops, isAbuGhurayb = False, isAlJazeera = False):
    possible = []
    for country in self.map:
      if isAbuGhurayb:
        if self.map[country].ally_Q() and self.map[country].governance != 4:
          possible.append(country)
      elif isAlJazeera:
        if country == "Saudi Arabia" or self.isAdjacent(country, "Saudi Arabia"):
          if self.map[country].troops() > 0:
            possible.append(country)
      elif (self.map[country].shia_mix_Q() or self.map[country].suni_Q()) and (self.map[country].good_Q() or self.map[country].fair_Q()) and (self.map[country].totalCells(True) > 0):
        if "Benazir Bhutto" in self.markers and country == "Pakistan":
          continue
        possible.append(country)
    if len(possible) == 0:
      return False
    else:
      countryScores = {}
      for country in possible:
        if self.map[country].good_Q():
          countryScores[country] = 2000000
        else:
          countryScores[country] = 1000000
        if country == "Pakistan":
          countryScores[country] += 100000
        if self.map[country].aid > 0:
          countryScores[country] += 10000
        if self.map[country].besieged > 0:
          countryScores[country] += 1000
        countryScores[country] += (self.countryResources(country) * 100)
        countryScores[country] += random.randint(1,99)
      countryOrder = []
      for country in countryScores:
        countryOrder.append((countryScores[country], (self.map[country].totalCells(True)), country))
      countryOrder.sort()
      countryOrder.reverse()
      returnList = []
      opsRemaining = ops
      for countryData in countryOrder:
        rolls = min(opsRemaining, countryData[1])
        returnList.append((countryData[2], rolls))
        opsRemaining -= rolls
        if opsRemaining <= 0:
          break
      return returnList

  def recruitChoice(self, ops, isMadrassas = False):

    self.debugprint(("DEBUG: recruit with remaining %d ops" % ops))

    self.debugprint(("DEBUG: recruit with remaining %d ops" % (2*ops)))


    countryScores = {}
    for country in self.map:


      if (self.map[country].totalCells(True) > 0 or (self.board.cadre_Q(country))) or (isMadrassas and self.map[country].governance > 2):
        #countryScores[country] = 0
        if (self.map[country].regime_change > 0) and (self.map[country].troops() - self.map[country].totalCells(True)) >= 5:
          self.debugprint(("a"))
          countryScores[country] = 100000000
        elif ((self.map[country].islamist_rule_Q()) and (self.map[country].totalCells(True) < (2 * ops))):
          davex = self.map[country].totalCells(True)
          self.debugprint(("here: recruit with remaining %d ops" % davex))
          countryScores[country] = 10000000
        elif (self.map[country].governance != 4) and (self.map[country].regime_change <= 0):
          self.debugprint(("b"))
          if self.map[country].recruit_req > 0:
            countryScores[country] = (self.map[country].recruit_req * 1000000)
          else:
            countryScores[country] = (self.map[country].governance * 1000000)
    for country in countryScores:
      self.debugprint(("c"))
      if self.map[country].besieged > 0:
        countryScores[country] += 100000
      countryScores[country] += (1000 * (self.map[country].troops() + self.map[country].totalCells(True)))
      countryScores[country] += 100 * self.countryResources(country)
      countryScores[country] += random.randint(1,99)
    countryOrder = []
    for country in countryScores:
      self.debugprint(("here: %d " % countryScores[country]))
      if countryScores[country] > 0:
        countryOrder.append((countryScores[country], (self.map[country].totalCells(True)), country))
    countryOrder.sort()
    countryOrder.reverse()
    if countryOrder == []:
      self.debugprint(("d"))
      return False
    else:
      self.debugprint(("e"))
      return countryOrder[0][2]

  def executeRecruit(self, country, ops, rolls, recruitOverride = None, isJihadistVideos = False, isMadrassas = False):
    self.outputToHistory("* Recruit to %s" % country)
    cellsRequested = ops
    if self.ideology >= 2:
      cellsRequested = ops * 2

    cells = self.numCellsAvailable(isMadrassas or isJihadistVideos)

    cellsToRecruit = min(cellsRequested, cells)
    if (self.map[country].regime_change or self.map[country].islamist_rule_Q()):
      if self.map[country].regime_change:
        self.outputToHistory("Recruit to Regime Change country automatically successful.", False)
      else:
        self.outputToHistory("Recruit to Islamic Rule country automatically successful.", False)
      self.cells -= cellsToRecruit
      self.map[country].sleeper_cells += cellsToRecruit

      if cellsToRecruit == 0 and isJihadistVideos:
        self.board.add_cadre(country)
        self.outputToHistory("No cells available to recruit.  Cadre added.", False)
        self.outputToHistory(self.board.country_summary(country), True)
        return ops - 1;
      else:
        self.board.remove_cadre(country)

      self.outputToHistory("%d sleeper cells recruited to %s." % (cellsToRecruit, country), False)
      self.outputToHistory(self.board.country_summary(country), True)
      if self.ideology >= 2:
        return ops - ((cellsToRecruit / 2) + (cellsToRecruit % 2))
      else:
        return (ops - cellsToRecruit)
    else:
      opsRemaining = ops
      i = 0

      if self.numCellsAvailable(isJihadistVideos) <= 0 and opsRemaining > 0:
        self.board.add_cadre(country)
        self.outputToHistory("No cells available to recruit.  Cadre added.", False)
        self.outputToHistory(self.board.country_summary(country), True)
        return ops - 1;
      else:
        while self.numCellsAvailable(isMadrassas or isJihadistVideos) > 0 and opsRemaining > 0:
          if recruitOverride:
            recVal = recruitOverride
          elif self.map[country].recruit_req > 0:
            recVal = self.map[country].recruit_req
          else:
            recVal = self.map[country].governance
          if rolls[i] <= recVal:
            if self.ideology >= 2:
              cellsMoving = min(self.numCellsAvailable(isMadrassas or isJihadistVideos), 2)
            else:
              cellsMoving = min(self.numCellsAvailable(isMadrassas or isJihadistVideos), 1)
            self.cells -= cellsMoving
            self.map[country].sleeper_cells += cellsMoving
            self.board.remove_cadre(country)
            self.outputToHistory("Roll successful, %d sleeper cell(s) recruited." % cellsMoving, False)
          else:
            self.outputToHistory("Roll failed.", False)
            if isJihadistVideos:
              self.board.add_cadre(country)
              self.outputToHistory("Cadre added.", False)
          opsRemaining -= 1
          i += 1
        self.outputToHistory(self.board.country_summary(country), True)
        return opsRemaining

  def handleRecruit(self, ops, isMadrassas = False):
    self.debugprint(("recruit ops: "))
    self.debugprint(("DEBUG: recruit with remaining %d ops" % ops))
    country = self.recruitChoice(ops, isMadrassas)
    if not country:
      self.outputToHistory("* No countries qualify to Recruit.", True)
      return ops
    else:
      if isMadrassas:
        cells = self.cells
      else:
        if "GTMO" in self.lapsing:
          self.outputToHistory("* Cannot Recruit due to GTMO.", True)
          return ops
        cells = self.numCellsAvailable()
      if cells <= 0:
        self.outputToHistory("* No cells available to Recruit.", True)
        return ops
      else:
        rolls = []
        for i in range(ops):
          rolls.append(random.randint(1,6))
        return self.executeRecruit(country, ops, rolls, None, False, isMadrassas)

  def isAdjacent(self, here, there):
    if "Patriot Act" in self.markers:
      if here == "United States" or there == "United States":
        if here == "Canada" or there == "Canada":
          return True
        else:
          return False
    if self.map[here] in self.map[there].links:
      return True
    if self.map[here].schengen and self.map[there].schengen:
      return True
    if self.map[here].schengenLink and self.map[there].schengen:
      return True
    if self.map[here].schengen and self.map[there].schengenLink:
      return True
    return False

  def adjacentCountryHasCell(self, targetCountry):
    for country in self.map:
      if self.isAdjacent(targetCountry, country):
        if (self.map[country].totalCells(True) > 0):
          return True
    return False

  def inLists(self, country, lists):
    for list in lists:
      if country in lists:
        return True
    return False

  def countryDistance(self, start, end):
    if start == end:
      return 0
    distanceGroups = []
    distanceGroups.append([start])
    distance = 1
    while not self.inLists(end, distanceGroups):
      list = distanceGroups[distance - 1]
      nextWave = []
      for country in list:
        for subCountry in self.map:
          if not self.inLists(subCountry, distanceGroups):
            if self.isAdjacent(subCountry, country):
              if subCountry == end:
                return distance
              if subCountry not in nextWave:
                nextWave.append(subCountry)
      distanceGroups.append(nextWave)
      distance += 1

  def travelDestinationChooseBasedOnPriority(self, countryList):
    for country in countryList:
      if country == "Pakistan":
        return country
    maxResources = 0
    for country in countryList:
      if self.countryResources(country) > maxResources:
        maxResources = self.countryResources(country)
    maxdests = []
    for country in countryList:
      if self.countryResources(country) == maxResources:
        maxdests.append(country)
    return random.choice(maxdests)

  def travelDestinations(self, ops, isRadicalization = False):
    dests = []
  # A non-Islamist Rule country with Regime Change, Besieged Regime, or Aid, if any
    if not isRadicalization:
      subdests = []
      for country in self.map:
        if (self.map[country].governance != 4) and ((self.map[country].besieged > 0) or (self.map[country].regime_change > 0) or (self.map[country].aid > 0)):
          if ("Biometrics" in self.lapsing) and (not self.adjacentCountryHasCell(country)):
            continue
          subdests.append(country)
      if len(subdests) == 1:
        dests.append(subdests[0])
      elif len(subdests) > 1:
        dests.append(self.travelDestinationChooseBasedOnPriority(subdests))
      if len(dests) == ops:
        return dests

  # A Poor country where Major Jihad would be possible if two (or fewer) cells were added.
    subdests = []
    for country in self.map:
      if (self.map[country].poor_Q()) and (((self.map[country].totalCells(True) + 2) - self.map[country].troops()) >= self.extraCellsNeededForMajorJihad()):
        if (not isRadicalization) and ("Biometrics" in self.lapsing) and (not self.adjacentCountryHasCell(country)):
          continue
        subdests.append(country)
    if len(subdests) == 1:
      dests.append(subdests[0])
    elif len(subdests) > 1:
      dests.append(self.travelDestinationChooseBasedOnPriority(subdests))
    if len(dests) == ops:
      return dests

  # A Good or Fair Muslim country with at least one cell adjacent.
    subdests = []
    for country in self.map:
      if ((self.map[country].good_Q()) or (self.map[country].fair_Q())) and ((self.map[country].suni_Q()) or (self.map[country].shia_mix_Q())):
        if self.adjacentCountryHasCell(country):
          if (not isRadicalization) and ("Biometrics" in self.lapsing) and (not self.adjacentCountryHasCell(country)):
            continue
          subdests.append(country)
    if len(subdests) == 1:
      dests.append(subdests[0])
    elif len(subdests) > 1:
      dests.append(self.travelDestinationChooseBasedOnPriority(subdests))
    if len(dests) == ops:
      return dests

  # An unmarked non-Muslim country if US Posture is Hard, or a Soft non-Muslim country if US Posture is Soft.
    subdests = []
    if self.map["United States"].hard_Q():
      for country in self.map:
        if self.map[country].non_muslim_Q() and self.map[country].test_posture_Q():
          if (not isRadicalization) and ("Biometrics" in self.lapsing) and (not self.adjacentCountryHasCell(country)):
            continue
          subdests.append(country)
    else:
      for country in self.map:
        if country != "United States" and self.map[country].non_muslim_Q() and self.map[country].soft_Q():
          if (not isRadicalization) and ("Biometrics" in self.lapsing) and (not self.adjacentCountryHasCell(country)):
            continue
          subdests.append(country)
    if len(subdests) == 1:
      dests.append(subdests[0])
    elif len(subdests) > 1:
      dests.append(random.choice(subdests))
    if len(dests) == ops:
      return dests

  # Random
    if (not isRadicalization) and ("Biometrics" in self.lapsing):
      subdests = []
      for country in self.map:
        if self.adjacentCountryHasCell(country):
          subdests.append(country)
      if len(subdests) > 0:
        while len(dests) < ops:
          dests.append(random.choice(subdests))
    else:
      while len(dests) < ops:
        dests.append(random.choice(list(self.map.keys())))

    return dests

  def travelDestinationsSchengenVisas(self):
    dests = []
  # An unmarked non-Muslim country if US Posture is Hard, or a Soft non-Muslim country if US Posture is Soft.
    subdests = []
    if self.map["United States"].hard_Q():
      for country in self.map:
        if self.map[country].schengen and self.map[country].test_posture_Q():
          subdests.append(country)
          print("SCHENGEN:", country)
    else:
      for country in self.map:
        if country != "United States" and self.map[country].schengen and self.map[country].soft_Q():
          subdests.append(country)
    if len(subdests) == 1:
      dests.append(subdests[0])
      dests.append(subdests[0])
    elif len(subdests) > 1:
      random.shuffle(subdests)
      dests.append(subdests[0])
      dests.append(subdests[1])
    elif len(subdests) == 0:
      for country in self.map:
        if self.map[country].schengen:
          subdests.append(country)
      random.shuffle(subdests)
      dests.append(subdests[0])
      dests.append(subdests[1])
    return dests

  def travelSourceChooseBasedOnPriority(self, countryList, i, destinations):
    subPossibles = []
    for country in countryList:
      if self.map[country].active_cells > 0:
        subPossibles.append(country)
    if len(subPossibles) == 1:
      return subPossibles[0]
    elif len(subPossibles) > 1:
      return random.choice(subPossibles)
    else:
      subPossibles = []
      for country in countryList:
        notAnotherDest = True
        for j in range(len(destinations)):
          if (i != j) and (country == destinations[j]):
            subPossibles.append(country)
    if len(subPossibles) == 1:
      return subPossibles[0]
    elif len(subPossibles) > 1:
      return random.choice(subPossibles)
    else:
      return random.choice(countryList)

  def travelSourceBoxOne(self, i, destinations, sources, ops, isRadicalization = False):
    possibles = []
    for country in self.map:
      if self.map[country].islamist_rule_Q():
        numTimesIsSource = 0
        for source in sources:
          if source == country:
            numTimesIsSource += 1
        if ((self.map[country].sleeper_cells + self.map[country].activeCells) - numTimesIsSource) > ops:
          if (not isRadicalization) and ("Biometrics" in self.lapsing) and (not self.isAdjacent(country, destinations[i])):
            continue
          possibles.append(country)
    if len(possibles) == 0:
      return False
    if len(possibles) == 1:
      return possibles[0]
    else:
      return self.travelSourceChooseBasedOnPriority(possibles, i, destinations)

  def travelSourceBoxTwo(self, i, destinations, sources, isRadicalization = False):
    possibles = []
    for country in self.map:
      if self.map[country].regime_change > 0:
        numTimesIsSource = 0
        for source in sources:
          if source == country:
            numTimesIsSource += 1
        if ((self.map[country].sleeper_cells + self.map[country].activeCells) - numTimesIsSource) > self.map[country].troops():
          if (not isRadicalization) and ("Biometrics" in self.lapsing) and (not self.isAdjacent(country, destinations[i])):
            continue
          possibles.append(country)
    if len(possibles) == 0:
      return False
    if len(possibles) == 1:
      return possibles[0]
    else:
      return self.travelSourceChooseBasedOnPriority(possibles, i, destinations)

  def travelSourceBoxThree(self, i, destinations, sources, isRadicalization = False):
    possibles = []
    for country in self.map:
      if self.isAdjacent(destinations[i], country):
        adjacent = self.map[country]
        numTimesIsSource = 0
        for source in sources:
          if source == adjacent.name:
            numTimesIsSource += 1
        if ((adjacent.sleeper_cells + adjacent.activeCells) - numTimesIsSource) > 0:
          if (not isRadicalization) and ("Biometrics" in self.lapsing) and (not self.isAdjacent(country, destinations[i])):
            continue
          possibles.append(adjacent.name)
    if len(possibles) == 0:
      return False
    if len(possibles) == 1:
      return possibles[0]
    else:
      return self.travelSourceChooseBasedOnPriority(possibles, i, destinations)

  def travelSourceBoxFour(self, i, destinations, sources, isRadicalization = False):
    possibles = []
    for country in self.map:
      numTimesIsSource = 0
      for source in sources:
        if source == country:
          numTimesIsSource += 1
      if ((self.map[country].sleeper_cells + self.map[country].activeCells) - numTimesIsSource) > 0:
        if (not isRadicalization) and ("Biometrics" in self.lapsing) and (not self.isAdjacent(country, destinations[i])):
          continue
        possibles.append(country)
    if len(possibles) == 0:
      return False
    if len(possibles) == 1:
      return possibles[0]
    else:
      return self.travelSourceChooseBasedOnPriority(possibles, i, destinations)

  def travelSources(self, destinations, ops, isRadicalization = False):
    sources = []
    for i in range(len(destinations)):
      source = self.travelSourceBoxOne(i, destinations, sources, ops, isRadicalization)
      if source:
        sources.append(source)
      else:
        source = self.travelSourceBoxTwo(i, destinations, sources, isRadicalization)
        if source:
          sources.append(source)
        else:
          source = self.travelSourceBoxThree(i, destinations, sources, isRadicalization)
          if source:
            sources.append(source)
          else:
            source = self.travelSourceBoxFour(i, destinations, sources, isRadicalization)
            if source:
              sources.append(source)
    return sources

  def testCountry(self, country):
    # Country testing if necessary
    if self.map[country].non_muslim_Q() and self.map[country].test_posture_Q():
      testRoll = random.randint(1,6)
      if testRoll <= 4:
        self.board.set_posture(country, Posture.SOFT)
      else:
        self.board.set_posture(country, Posture.HARD)
      self.outputToHistory("%s tested, posture %s" % (self.map[country].name, self.map[country].posture), False)
    elif self.map[country].governance == 0:
      testRoll = random.randint(1,6)
      if testRoll <= 4:
        self.map[country].governance = 3
      else:
        self.map[country].governance = 2
      self.map[country].alignment = "Neutral"
      self.outputToHistory("%s tested, governance %s" % (self.map[country].name, self.map[country].govStr()), False)

  def getCountriesWithUSPostureByGovernance(self):
    dict = {}
    dict["Good"] = []
    dict["Fair"] = []
    dict["Poor"] = []
    for country in self.map:
      if (country != "United States") and (self.map[country].posture == self.map["United States"].posture):
        if self.map[country].good_Q():
          dict["Good"].append(country)
        elif self.map[country].fair_Q():
          dict["Fair"].append(country)
        elif self.map[country].poor_Q():
          dict["Poor"].append(country)
    return dict

  def getCountriesWithTroopsByGovernance(self):
    dict = {}
    dict["Good"] = []
    dict["Fair"] = []
    dict["Poor"] = []
    for country in self.map:
      if self.map[country].troops() > 0:
        if self.map[country].good_Q():
          dict["Good"].append(country)
        elif self.map[country].fair_Q():
          dict["Fair"].append(country)
        elif self.map[country].poor_Q():
          dict["Poor"].append(country)
    return dict

  def getCountriesWithAidByGovernance(self):
    dict = {}
    dict["Good"] = []
    dict["Fair"] = []
    dict["Poor"] = []
    for country in self.map:
      if self.map[country].aid > 0:
        if self.map[country].good_Q():
          dict["Good"].append(country)
        elif self.map[country].fair_Q():
          dict["Fair"].append(country)
        elif self.map[country].poor_Q():
          dict["Poor"].append(country)
    return dict

  def getNonMuslimCountriesByGovernance(self):
    dict = {}
    dict["Good"] = []
    dict["Fair"] = []
    dict["Poor"] = []
    for country in self.map:
      if (country != "United States") and (self.map[country].non_muslim_Q()):
        if self.map[country].good_Q():
          dict["Good"].append(country)
        elif self.map[country].fair_Q():
          dict["Fair"].append(country)
        elif self.map[country].poor_Q():
          dict["Poor"].append(country)
    return dict

  def getMuslimCountriesByGovernance(self):
    dict = {}
    dict["Good"] = []
    dict["Fair"] = []
    dict["Poor"] = []
    for country in self.map:
      if self.map[country].culture != "Non-Muslim":
        if self.map[country].good_Q():
          dict["Good"].append(country)
        elif self.map[country].fair_Q():
          dict["Fair"].append(country)
        elif self.map[country].poor_Q():
          dict["Poor"].append(country)
    return dict

  def handleTravel(self, ops, isRadicalization = False, isSchengenVisas = False, isCleanOperatives = False):
    if isSchengenVisas:
      destinations = self.travelDestinationsSchengenVisas()
    elif isCleanOperatives:
      destinations = ["United States", "United States"]
    else:
      destinations = self.travelDestinations(ops, isRadicalization)
    sources = self.travelSources(destinations, ops, isRadicalization)
    if not isRadicalization and not isSchengenVisas and not isCleanOperatives:
      self.outputToHistory("* Cells Travel", False)
    for i in range(len(sources)):
      self.outputToHistory("->Travel from %s to %s." % (sources[i], destinations[i]), False)
      success = False
      displayStr = "BLAH!!"
      if isRadicalization:
        success = True
        displayStr = ("Travel by Radicalization is automatically successful.")
      elif isSchengenVisas:
        success = True
        displayStr = ("Travel by Schengen Visas is automatically successful.")
      elif isCleanOperatives:
        success = True
        displayStr = ("Travel by Clean Operatives is automatically successful.")
      else:
        if sources[i] == destinations[i]:
          success = True
          displayStr = ("Travel within country automatically successful.")
        else:
          if self.isAdjacent(sources[i], destinations[i]):
            if not "Biometrics" in self.lapsing:
              success = True
              displayStr = ("Travel to adjacent country automatically successful.")
            else:
              roll = random.randint(1,6)
              if roll <= self.map[destinations[i]].governance:
                success = True
                displayStr = ("Travel roll needed due to Biometrics - roll successful.")
              else:
                displayStr = ("Travel roll needed due to Biometrics -  roll failed, cell to funding track.")
          else:
            roll = random.randint(1,6)
            if roll <= self.map[destinations[i]].governance:
              success = True
              displayStr = ("Travel roll successful.")
            else:
              displayStr = ("Travel roll failed, cell to funding track.")
      self.outputToHistory(displayStr, True)
      self.testCountry(destinations[i])
      if success:
        if self.map[sources[i]].active_cells > 0:
          self.map[sources[i]].active_cells -= 1
        else:
          self.map[sources[i]].sleeper_cells -= 1
        self.map[destinations[i]].sleeper_cells += 1
        self.outputToHistory(self.board.country_summary(sources[i]), False)
        self.outputToHistory(self.board.country_summary(destinations[i]), True)
      else:
        if self.map[sources[i]].active_cells > 0:
          self.map[sources[i]].active_cells -= 1
        else:
          self.map[sources[i]].sleeper_cells -= 1
        self.cells += 1
        self.outputToHistory(self.board.country_summary(sources[i]), True)
    return ops - len(sources)

  def placePlots(self, country, rollPosition, plotRolls, isMartydomOperation = False, isDanishCartoons = False, isKSM = False):
    if (self.map[country].totalCells(True)) > 0:
      if isMartydomOperation:
        self.removeCell(country)
        self.outputToHistory("Place 2 available plots in %s." % country, False)
        self.map[country].plots += 2
        rollPosition = 1
      elif isDanishCartoons:
        if self.numIslamcRule() > 0:
          self.outputToHistory("Place any available plot in %s." % country, False)
        else:
          self.outputToHistory("Place a Plot 1 in %s." % country, False)
        self.map[country].plots += 1
        rollPosition = 1
      elif isKSM:
        if self.map[country] != 4:
          self.outputToHistory("Place any available plot in %s." % country, False)
          self.map[country].plots += 1
          rollPosition = 1
      else:
        opsRemaining = len(plotRolls) - rollPosition
        cellsAvailable = self.map[country].totalCells(True)
        plotsToPlace = min(cellsAvailable, opsRemaining)
        self.outputToHistory("--> %s plot attempt(s) in %s." % (plotsToPlace, country), False)
        successes = 0
        failures = 0
        for i in range(rollPosition, rollPosition + plotsToPlace):
          if plotRolls[i] <= self.map[country].governance:
            successes += 1
          else:
            failures += 1
        self.outputToHistory("Plot rolls: %d Successes rolled, %d Failures rolled" % (successes, failures), False)
        for i in range(plotsToPlace - self.map[country].numActiveCells()):
          self.outputToHistory("Cell goes Active", False)
          self.map[country].sleeper_cells -= 1
          self.map[country].active_cells += 1
        self.map[country].plots += successes
        self.outputToHistory("%d Plot(s) placed in %s." % (successes, country), False)
        if "Abu Sayyaf" in self.markers and country == "Philippines" and self.map[country].troops() <= self.map[country].totalCells() and successes > 0:
          self.outputToHistory("Prestige loss due to Abu Sayyaf.", False)
          self.changePrestige(-successes)
        if "NEST" in self.markers and country == "Unites States":
          self.outputToHistory("NEST in play. If jihadists have WMD, all plots in the US placed face up.", False)
        self.outputToHistory(self.board.country_summary(country), True)
        rollPosition += plotsToPlace
    return rollPosition

  def handlePlotPriorities(self, countriesDict, ops, rollPosition, plotRolls, isOps, isMartydomOperation = False, isDanishCartoons = False, isKSM = False):
    if isOps:
      if len(countriesDict["Fair"]) > 0:
        targets = countriesDict["Fair"]
        random.shuffle(targets)
        i = 0
        while rollPosition < ops and i < len(targets):
          rollPosition = self.placePlots(targets[i], rollPosition, plotRolls, isMartydomOperation, isDanishCartoons, isKSM)
          i += 1
      if rollPosition == ops:
        return rollPosition
      if len(countriesDict["Good"]) > 0:
        targets = countriesDict["Good"]
        random.shuffle(targets)
        i = 0
        while rollPosition < ops and i < len(targets):
          rollPosition = self.placePlots(targets[i], rollPosition, plotRolls, isMartydomOperation, isDanishCartoons, isKSM)
          i += 1
      if rollPosition == ops:
        return rollPosition
    else:
      if len(countriesDict["Good"]) > 0:
        targets = countriesDict["Good"]
        random.shuffle(targets)
        i = 0
        while rollPosition < ops and i < len(targets):
          rollPosition = self.placePlots(targets[i], rollPosition, plotRolls, isMartydomOperation, isDanishCartoons, isKSM)
          i += 1
      if rollPosition == ops:
        return rollPosition
      if len(countriesDict["Fair"]) > 0:
        targets = countriesDict["Fair"]
        random.shuffle(targets)
        i = 0
        while rollPosition < ops and i < len(targets):
          rollPosition = self.placePlots(targets[i], rollPosition, plotRolls, isMartydomOperation, isDanishCartoons, isKSM)
          i += 1
      if rollPosition == ops:
        return rollPosition
    if len(countriesDict["Poor"]) > 0:
      targets = countriesDict["Poor"]
      random.shuffle(targets)
      i = 0
      while rollPosition < ops and i < len(targets):
        rollPosition = self.placePlots(targets[i], rollPosition, plotRolls, isMartydomOperation, isDanishCartoons, isKSM)
        i += 1
    return rollPosition

  def executePlot(self, ops, isOps, plotRolls, isMartydomOperation = False, isDanishCartoons = False, isKSM = False):
    if not isMartydomOperation and not isDanishCartoons and not isKSM:
      self.outputToHistory("* Jihadists Plotting", False)
  # In US
    self.debugprint(("DEBUG: In US"))
    rollPosition = self.placePlots("United States", 0, plotRolls, isMartydomOperation, isDanishCartoons, isKSM)
    if rollPosition == ops:
      return 0
    if self.board.prestige_track.get_prestige() >= 4:
  # Prestige high
      self.debugprint(("DEBUG: Prestige high"))
      if ("Abu Sayyaf" in self.markers) and ((self.map["Philippines"].totalCells(True)) >= self.map["Philippines"].troops()):
  # In Philippines
        self.debugprint(("DEBUG: Philippines"))
        rollPosition = self.placePlots("Philippines", rollPosition, plotRolls, isMartydomOperation, isDanishCartoons, isKSM)
        if rollPosition == ops:
          return 0
  # With troops
      self.debugprint(("DEBUG: troops"))
      troopDict = self.getCountriesWithTroopsByGovernance()
      rollPosition = self.handlePlotPriorities(troopDict, ops, rollPosition, plotRolls, isOps, isMartydomOperation, isDanishCartoons, isKSM)
      if rollPosition == ops:
        return 0
  # No GWOT Penalty
    if self.board.gwot()['penalty'] >= 0:
      self.debugprint(("DEBUG: No GWOT Penalty"))
      postureDict = self.getCountriesWithUSPostureByGovernance()
      rollPosition = self.handlePlotPriorities(postureDict, ops, rollPosition, plotRolls, isOps, isMartydomOperation, isDanishCartoons, isKSM)
      if rollPosition == ops:
        return 0
  # With aid
    self.debugprint(("DEBUG: aid"))
    aidDict = self.getCountriesWithAidByGovernance()
    rollPosition = self.handlePlotPriorities(aidDict, ops, rollPosition, plotRolls, isOps, isMartydomOperation, isDanishCartoons, isKSM)
    if rollPosition == ops:
      return 0
  # Funding < 9
    if self.funding < 9:
      self.debugprint(("DEBUG: Funding < 9"))
      nonMuslimDict = self.getNonMuslimCountriesByGovernance()
      rollPosition = self.handlePlotPriorities(nonMuslimDict, ops, rollPosition, plotRolls, isOps, isMartydomOperation, isDanishCartoons, isKSM)
      if rollPosition == ops:
        return 0
      muslimDict = self.getMuslimCountriesByGovernance()
      rollPosition = self.handlePlotPriorities(muslimDict, ops, rollPosition, plotRolls, isOps, isMartydomOperation, isDanishCartoons, isKSM)
      if rollPosition == ops:
        return 0
    return len(plotRolls) - rollPosition

  def handlePlot(self, ops, isOps):
    plotRolls = []
    for i in range(ops):
      plotRolls.append(random.randint(1,6))
    return self.executePlot(ops, isOps, plotRolls)

  def handleRadicalization(self, ops):
    self.outputToHistory("* Radicaliztion with %d ops." % ops, False)
    opsRemaining = ops
  # First box
    if opsRemaining > 0:
      if self.cells > 0:
        country = random.choice(list(self.map.keys()))
        self.map[country].sleeper_cells += 1
        self.cells -= 1
        self.outputToHistory("--> Cell placed in %s." % country, True)
        self.testCountry(country)
        self.outputToHistory(self.board.country_summary(country), True)
        opsRemaining -= 1
  # Second box
    if opsRemaining > 0:
      if self.cells < 15:
        self.handleTravel(1, True)
        opsRemaining -= 1
  # Third box
    if opsRemaining > 0:
      if self.funding < 9:
        possibles = []
        for country in self.map:
          if self.map[country].governance != 4:
            if (self.map[country].totalCells(True)) > 0:
              possibles.append(country)
        if len(possibles) > 0:
          location = random.choice(possibles)
          self.testCountry(location)
          self.map[location].plots += 1
          self.outputToHistory("--> Plot placed in %s." % location, True)
#           if self.map[location].active_cells == 0:
#             self.map[location].active_cells += 1
#             self.map[location].sleeper_cells -= 1
          opsRemaining -= 1
  # Fourth box
    while opsRemaining > 0:
      possibles = []
      for country in self.map:
        if (self.map[country].shia_mix_Q() or self.map[country].suni_Q()) and (self.map[country].good_Q() or self.map[country].fair_Q()):
          possibles.append(country)
      if len(possibles) == 0:
        self.outputToHistory("--> No remaining Good or Fair countries.", True)
        break
      else:
        location = random.choice(possibles)
        self.map[location].governance += 1
        self.outputToHistory("--> Governance in %s worsens to %s." % (location, self.map[location].govStr()), True)
        self.outputToHistory(self.board.country_summary(location), True)
        opsRemaining -= 1

  def resolvePlot(self, country, plotType, postureRoll, usPrestigeRolls, schCountries, schPostureRolls, govRolls, isBacklash = False):
    self.outputToHistory("--> Resolve \"%s\" plot in %s" % (str(plotType), country), False)
    if country == "United States":
      if plotType == "WMD":
        self.gameOver = True
        self.outputToHistory("== GAME OVER - JIHADIST AUTOMATIC VICTORY ==", True)
      else:
        self.funding = 9
        self.outputToHistory("Jihadist Funding now 9", False)
        presMultiplier = 1
        if usPrestigeRolls[0] <= 4:
          presMultiplier = -1
        self.changePrestige(min(usPrestigeRolls[1], usPrestigeRolls[2]) * presMultiplier)
        self.outputToHistory("US Prestige now %d" % self.prestige, False)
        if postureRoll <= 4:
          self.board.set_posture("United States", Posture.SOFT)
        else:
          self.board.set_posture("United States", Posture.HARD)
        self.outputToHistory("US Posture now %s" % self.map["United States"].posture, True)
    elif self.map[country].culture != "Non-Muslim":
      if not isBacklash:
        if self.map[country].good_Q():
          self.changeFunding(2)
        else:
          self.changeFunding(1)
        self.outputToHistory("Jihadist Funding now %d" % self.funding, False)
      else:
        if plotType == "WMD":
          self.funding = 1
        else:
          self.funding -= 1
          if self.map[country].good_Q():
            self.funding -= 1
          if self.funding < 1:
            self.funding = 1
        self.outputToHistory("BACKLASH: Jihadist Funding now %d" % self.funding, False)
      if self.map[country].troops() > 0:
        if plotType == "WMD":
          self.board.prestige_track.set_prestige(1)
        else:
          self.prestige_track.dec_prestige(1)
        if self.board.prestige_track.get_prestige() < 1:
          self.board.prestige_track.set_prestige(1)
        self.outputToHistory("Troops present so US Prestige now %d" % self.prestige, False)
      if country != "Iran":
        successes = 0
        failures = 0
        for roll in govRolls:
          if roll <= self.map[country].governance:
            successes += 1
          else:
            failures += 1
        self.outputToHistory("Governance rolls: %d Successes rolled, %d Failures rolled" % (successes, failures), False)
        if self.map[country].aid and successes > 0:
          self.map[country].aid = 0
          self.outputToHistory("Aid removed.", False)
        if self.map[country].poor_Q() and successes > 0:
          self.outputToHistory("Governance stays at %s" % self.map[country].govStr(), True)
        while successes > 0 and self.map[country].governance < 3:
          self.map[country].governance += 1
          successes -= 1
          self.outputToHistory("Governance to %s" % self.map[country].govStr(), True)
    elif self.map[country].non_muslim_Q():
      if country == "Israel" and "Abbas" in self.markers:
        self.markers.remove("Abbas")
        self.outputToHistory("Abbas no longer in play.", True)
      if country == "India" and "Indo-Pakistani Talks" in self.markers:
        self.markers.remove("Indo-Pakistani Talks")
        self.outputToHistory("Indo-Pakistani Talks no longer in play.", True)
      if plotType == "WMD":
        self.funding = 9
      else:
        if self.map[country].good_Q():
          self.changeFunding(plotType * 2)
        else:
          self.changeFunding(plotType)
      self.outputToHistory("Jihadist Funding now %d" % self.funding, False)
      if country != "Israel":
        if postureRoll <= 4:
          self.board.set_posture(country, Posture.SOFT)
        else:
          self.board.set_posture(country, Posture.HARD)
        self.outputToHistory("%s Posture now %s" % (country, self.map[country].posture), True)

      if self.map[country].troops() > 0:
        if plotType == "WMD":
          self.board.prestige_track.set_prestige(1)
        else:
          self.prestige_track.dec_prestige(1)
        if self.board.prestige_track.get_prestige() < 1:
          self.board.prestige_track.set_prestige(1)
        self.outputToHistory("Troops present so US Prestige now %d" % self.prestige, False)


      if self.map[country].schengen:
        for i in range(len(schCountries)):
          if schPostureRolls[i] <= 4:
            self.board.set_posture(schCountries[i], Posture.SOFT)
          else:
            self.board.set_posture(schCountries[i], Posture.HARD)
          self.outputToHistory("%s Posture now %s" % (schCountries[i], self.map[schCountries[i]].posture), False)
      self.outputToHistory("", False)
    self.map[country].plots -= 1
    if self.map[country].plots < 0:
      self.map[country].plots = 0

  def eventPutsCell(self, cardNum):
    return self.deck[str(cardNum)].putsCell(self)

  def playableNonUSEvent(self, cardNum):
    return self.deck[str(cardNum)].type != "US" and  self.deck[str(cardNum)].playable("Jihadist", self)
    return False

  def playableUSEvent(self, cardNum):
    return self.deck[str(cardNum)].type == "US" and  self.deck[str(cardNum)].playable("US", self)

  def aiFlowChartTop(self, cardNum):
    self.debugprint(("DEBUG: START"))
    self.debugprint(("DEBUG: Playble Non-US event? [1]"))
    if self.playableNonUSEvent(cardNum):
      self.debugprint(("DEBUG: YES"))
      self.outputToHistory("Playable Non-US Event.", False)
      self.debugprint(("Event Recruits or places cell? [2]"))
      if self.eventPutsCell(cardNum):
        self.debugprint(("DEBUG: YES"))
        self.debugprint(("Track has cell? [3]"))
        if self.cells > 0:
          self.debugprint(("DEBUG: YES"))
          self.aiFlowChartPlayEvent(cardNum)
        else:
          self.debugprint(("DEBUG: NO"))
          self.debugprint(("DEBUG: Radicalization [4]"))
          self.handleRadicalization(self.deck[str(cardNum)].ops)
      else:
        self.debugprint(("DEBUG: NO"))
        self.aiFlowChartPlayEvent(cardNum)
    else:
      self.debugprint(("DEBUG: NO"))
      self.debugprint(("DEBUG: Playble US event? [7]"))
      if self.playableUSEvent(cardNum):
        self.debugprint(("DEBUG: YES"))
        self.debugprint(("DEBUG: Plot Here [5]"))
        self.outputToHistory("Playable US Event.", False)
        unusedOps = self.handlePlot(self.deck[str(cardNum)].ops, True)
        if unusedOps > 0:
          self.debugprint(("DEBUG: Radicalization with remaining %d ops" % unusedOps))
          self.handleRadicalization(unusedOps)
        self.debugprint(("DEBUG: END"))
      else:
        self.debugprint(("DEBUG: NO"))
        self.outputToHistory("Unplayable Event. Using Ops for Operations.", False)
        self.aiFlowChartMajorJihad(cardNum)

  def aiFlowChartPlayEvent(self, cardNum):
    self.debugprint(("Play Event [6]"))
    self.deck[str(cardNum)].playEvent("Jihadist", self)
    self.debugprint(("Unassociated Event? [8]"))
    if self.deck[str(cardNum)].type == "Unassociated":
      self.debugprint(("DEBUG: YES"))
      self.outputToHistory("Unassociated event now being used for Ops.", False)
      self.aiFlowChartMajorJihad(cardNum)
    else:
      self.debugprint(("DEBUG: NO"))
      self.debugprint(("end [9]"))

  def aiFlowChartMajorJihad(self, cardNum):
    self.debugprint(("DEBUG: Major Jihad success possible? [10]"))
    country = self.majorJihadChoice(self.deck[str(cardNum)].ops)
    if country:
      self.debugprint(("DEBUG: YES"))
      self.debugprint(("DEBUG: Major Jihad [11]"))
      unusedOps = self.handleJihad(country, self.deck[str(cardNum)].ops)
      if unusedOps > 0:
        self.debugprint(("DEBUG: Radicalization with remaining %d ops" % unusedOps))
        self.handleRadicalization(unusedOps)
    else:
      self.debugprint(("DEBUG: NO"))
      self.debugprint(("DEBUG: Jihad possible in Good/Fair? [12]"))
      countryList = self.minorJihadInGoodFairChoice(self.deck[str(cardNum)].ops)
      if countryList:
        self.debugprint(("DEBUG: YES"))
        unusedOps = self.handleMinorJihad(countryList, self.deck[str(cardNum)].ops)
        if unusedOps > 0:
          self.debugprint(("DEBUG: Radicalization with remaining %d ops" % unusedOps))
          self.handleRadicalization(unusedOps)
      else:
        self.debugprint(("DEBUG: NO"))
        self.debugprint(("DEBUG: Cells Available? [14]"))
        if self.numCellsAvailable() > 0:
          self.debugprint(("DEBUG: YES"))
          self.debugprint(("DEBUG: Recruit [15]"))
          unusedOps = self.handleRecruit(self.deck[str(cardNum)].ops)
          if unusedOps > 0:
            self.debugprint(("DEBUG: Radicalization with remaining %d ops" % unusedOps))
            self.handleRadicalization(unusedOps)
        else:
          self.debugprint(("DEBUG: NO"))
          self.debugprint(("DEBUG: Travel [16]"))
          unusedOps = self.handleTravel(self.deck[str(cardNum)].ops)
          if unusedOps > 0:
            self.debugprint(("DEBUG: Radicalization with remaining %d ops" % unusedOps))
            self.handleRadicalization(unusedOps)

  def executeNonMuslimWOI(self, country, postureRoll):
    if postureRoll > 4:
      self.board.set_posture(country, "Hard")
      self.outputToHistory("* War of Ideas in %s - Posture Hard" % country, False)
      if self.map["United States"].hard_Q():
        self.changePrestige(1)
    else:
      self.board.set_posture(country, "Soft")
      self.outputToHistory("* War of Ideas in %s - Posture Soft" % country, False)
      if self.map["United States"].soft_Q():
        self.changePrestige(1)

  def executeCardEuroIslam(self, posStr):
    self.board.set_posture("Benelux", posStr)
    if self.numIslamicRule() == 0:
      self.funding -= 1
      if self.funding < 1:
        self.funding = 1
      self.outputToHistory("Jihadist Funding now %d" % self.funding, False)
    self.outputToHistory(self.board.country_summary("Benelux"), True)

  def executeCardLetsRoll(self, plotCountry, postureCountry, postureStr):
    self.map[plotCountry].plots = max(0, self.map[plotCountry].plots - 1)
    self.outputToHistory("Plot removed from %s." % plotCountry, False)
    self.board.set_posture(postureCountry, postureStr)
    self.outputToHistory("%s Posture now %s." % (postureCountry, postureStr), False)
    self.outputToHistory(self.board.country_summary(plotCountry), False)
    self.outputToHistory(self.board.country_summary(postureCountry), True)

  def executeCardHEU(self, country, roll):
    if roll <= self.map[country].governance:
      self.outputToHistory("Add a WMD to available Plots.", True)
    else:
      self.removeCell(country)

  def executeCardUSElection(self, postureRoll):
    if postureRoll <= 4:
      self.board.set_posture("United States", "Soft")
      self.outputToHistory("United States Posture now Soft.", False)
    else:
      self.board.set_posture("United States", "Hard")
      self.outputToHistory("United States Posture now Hard.", False)
    if self.board.gwot()['penalty'] == 0:
      self.changePrestige(1)
    else:
      self.changePrestige(-1)

  def listCountriesInParam(self, needed = None):
    print("")
    print("Contries")
    print("--------")
    for country in needed:
      print(self.board.country_summary(country))
    print("")

  def listCountriesWithTroops(self, needed = None):
    print("")
    print("Contries with Troops")
    print("--------------------")
    if needed == None:
      needed = 0
    if self.board.troop_track.get_troops() > needed:
      print("Troop Track: %d" % self.board.troop_track.get_troops())
    for country in self.map:
      if self.map[country].troops() > needed:
        print("%s: %d" % (country, self.map[country].troops()))
    print("")

  def listDeployOptions(self, na = None):
    print("")
    print("Deploy Options")
    print("--------------")
    for country in self.map:
      if self.map[country].ally_Q() or ("Abu Sayyaf" in self.markers and country == "Philippines"):
        print("%s: %d troops" % (country, self.map[country].troops()))
    print("")

  def listDisruptableCountries(self, na = None):
    print("")
    print("Disruptable Countries")
    print("--------------------")
    for country in self.map:
      if self.map[country].sleeper_cells + self.map[country].active_cells > 0 or self.board.cadre_Q(country):
        if self.map[country].troops() > 0 or self.map[country].non_muslim_Q() or self.map[country].ally_Q():
          postureStr = ""
          troopsStr = ""
          if self.map[country].non_muslim_Q():
            postureStr = ", Posture %s" % self.map[country].posture
          else:
            troopsStr = ", Troops: %d" % self.map[country].troops()
          print("%s - %d Active Cells, %d Sleeper Cells, %d Cadre%s%s" % (country, self.map[country].activeCells, self.map[country].sleeper_cells, self.map[country].cadre, troopsStr, postureStr))
    print("")

  def listWoICountries(self, na = None):
    print("")
    print("War of Ideas Eligible Countries")
    print("-------------------------------")
    for country in self.map:
      if self.map[country].alignment == "Neutral" or self.map[country].ally_Q() or self.map[country].governance == 0:
        print("%s, %s %s - %d Active Cells, %d Sleeper Cells, %d Cadre, %d troops" % (country, self.map[country].govStr(), self.map[country].alignment, self.map[country].activeCells, self.map[country].sleeper_cells, self.map[country].cadre, self.map[country].troops()))
    for country in self.map:
      if self.map[country].non_muslim_Q() and country != "United States" and self.map[country].hard_Q():
        print("%s, Posture %s" % (country, self.map[country].posture))
    for country in self.map:
      if self.map[country].non_muslim_Q() and country != "United States" and self.map[country].soft_Q():
        print("%s, Posture %s" % (country, self.map[country].posture))
    for country in self.map:
      if self.map[country].non_muslim_Q() and country != "United States" and self.map[country].test_posture_Q():
        print("%s, Untested" % country)

  def listPlotCountries(self, na = None):
    print("")
    print("Contries with Active Plots")
    print("--------------------------")
    for country in self.map:
      if self.map[country].plots > 0:
        print(self.board.country_summary(country))
    print("")

  def listIslamicCountries(self, na = None):
    print("")
    print("Islamic Rule Countries")
    print("----------------------")
    for country in self.map:
      if self.map[country].islamist_rule_Q():
        print(self.board.country_summary(country))
    print("")

  def listRegimeChangeCountries(self, na = None):
    print("")
    print("Regime Change Countries")
    print("-----------------------")
    for country in self.map:
      if self.map[country].regime_change > 0:
        print(self.board.country_summary(country))
    print("")

  def listRegimeChangeWithTwoCells(self, na = None):
    print("")
    print("Regime Change Countries with Two Cells")
    print("---------------------------------------")
    for country in self.map:
      if self.map[country].regime_change > 0:
        if self.map[country].totalCells() >= 2:
          print(self.board.country_summary(country))
    print("")

  def listCountriesWithCellAndAdjacentTroops(self, na = None):
    print("")
    print("Countries with Cells and with Troops or adjacent to Troops")
    print("----------------------------------------------------------")
    for country in self.map:
      if self.map[country].totalCells(True) > 0:
        if self.map[country].troops() > 0:
          print(self.board.country_summary(country))
        else:
          for subCountry in self.map:
            if subCountry != country:
              if self.map[subCountry].troops() > 0 and self.isAdjacent(country, subCountry):
                print(self.board.country_summary(country))
                break
    print("")

  def listAdversaryCountries(self, na = None):
    print("")
    print("Adversary Countries")
    print("-------------------")
    for country in self.map:
      if self.map[country].alignment == "Adversary":
        print(self.board.country_summary(country))
    print("")

  def listGoodAllyPlotCountries(self, na = None):
    print("")
    print("Ally or Good Countries with Plots")
    print("---------------------------------")
    for country in self.map:
      if self.map[country].plots > 0:
        if self.map[country].ally_Q() or self.map[country].good_Q():
          print(self.board.country_summary(country))
    print("")

  def listMuslimCountriesWithCells(self, na = None):
    print("")
    print("Muslim Countries with Cells")
    print("---------------------------")
    for country in self.map:
      if self.map[country].totalCells(True) > 0:
        if self.map[country].shia_mix_Q() or self.map[country].suni_Q():
          print(self.board.country_summary(country))
    print("")

  def listBesiegedCountries(self, na = None):
    print("")
    print("Besieged Regimes")
    print("----------------")
    for country in self.map:
      if self.map[country].besieged > 0:
        print(self.board.country_summary(country))
    print("")

  def listShiaMixRegimeChangeCountriesWithCells(self, na = None):
    print("")
    print("Shia-Mix Regime Change Countries with Cells")
    print("-------------------------------------------")
    for country in self.map:
      if self.map[country].shia_mix_Q():
        if self.map[country].regime_change > 0:
          if (self.map[country].totalCells(True)) > 0:
            print(self.board.country_summary(country))
    print("")

  def listShiaMixCountries(self, na = None):
    print("")
    print("Shia-Mix Countries")
    print("------------------")
    for country in self.map:
      if self.map[country].shia_mix_Q():
        print(self.board.country_summary(country))
    print("")

  def listShiaMixCountriesWithCellsTroops(self, na = None):
    print("")
    print("Shia-Mix Countries with Cells and Troops")
    print("----------------------------------------")
    for country in self.map:
      if self.map[country].shia_mix_Q():
        if self.map[country].troops() > 0 and self.map[country].totalCells() > 0:
          print(self.board.country_summary(country))
    print("")

  def listSchengenCountries(self, na = None):
    print("")
    print("Schengen Countries")
    print("------------------")
    for country in self.map:
      if self.map[country].schengen > 0:
        print(self.board.country_summary(country))
    print("")

  def listHambali(self, na = None):
    print("")
    print("Indonesia or adjacent country with cell and Ally or Hard")
    print("--------------------------------------------------------")
    possibles = ["Indonesia/Malaysia"]
    for countryObj in self.map["Indonesia/Malaysia"].links:
      possibles.append(countryObj.name)
    for country in possibles:
      if self.map[country].totalCells(True) > 0:
        if self.map[country].non_muslim_Q():
          if self.map[country].hard_Q():
            print(self.board.country_summary(country))
        else:
          if self.map[country].ally_Q():
            print(self.board.country_summary(country))


  def do_history(self,rest):

    if rest == 'save':
      f = open('history.txt','w')
      for str in self.history:
        f.write(str + "\r\n")
      f.close()

    for str in self.history:
      print(str)
    print("")

  def help_history(self):
    print("Display Game History.  Type 'history save' to save history to a file called history.txt.")
    print("")


  def do_disrupt(self, rest):
    where = None
    sleepers = 0
    actives = 0
    while not where:
      input = self.getCountryFromUser("Disrupt what country?  (? for list): ",  "XXX", self.listDisruptableCountries)
      if input == "":
        print("")
        return
      else:
        if self.map[input].sleeper_cells + self.map[input].active_cells <= 0 and not self.board.cadre_Q(input) :
          print("There are no cells or cadre in %s." % input)
          print("")
        elif "FATA" in self.map[input].markers and self.map[input].regime_change == 0:
          print("No disrupt allowed due to FATA.")
          print("")
        elif self.map[input].troops() > 0 or self.map[input].non_muslim_Q() or self.map[input].ally_Q():
          #print("Disrupt in %s - %d Active Cells, %d Sleeper Cells" % (input, self.map[input].activeCells, self.map[input].sleeper_cells))
          print("")
          where = input
          sleepers = self.map[input].sleeper_cells
          actives = self.map[input].activeCells
        else:
          print("You can't disrupt there.")
          print("")
    self.handleDisrupt(where)

  def help_disrupt(self):
    print("Disrupt Cells or Cadre.")
    print("")

  def do_woi(self, rest):
    where = None
    while not where:
      input = self.getCountryFromUser("War of Ideas in what country?  (? for list): ", "XXX", self.listWoICountries)
      if input == "":
        print("")
        return
      else:
        if self.map[input].non_muslim_Q() and input != "United States":
          where = input
        elif self.map[input].ally_Q() or self.map[input].alignment == "Neutral" or self.map[input].governance == 0:
          where = input
        else:
          print("Country not eligible for War of Ideas.")
          print("")
    if self.map[where].non_muslim_Q() and input != "United States": # Non-Muslim
      postureRoll = self.getRollFromUser("Enter Posture Roll or r to have program roll: ")
      if postureRoll > 4:
        self.board.set_posture(where, "Hard")
        self.outputToHistory("* War of Ideas in %s - Posture Hard" % where)
        if self.map["United States"].hard_Q():
          self.board.prestige_track.inc_prestige(1)
          if self.board.prestige_track.get_prestige() > 12:
            self.board.prestige_track.set_prestige(12)
          self.outputToHistory("US Prestige now %d" % self.board.prestige_track.get_prestige())
      else:
        self.board.set_posture(where, "Soft")
        self.outputToHistory("* War of Ideas in %s - Posture Soft" % where)
        if self.map["United States"].soft_Q():
          self.board.prestige_track.inc_prestige(1)
          if self.board.prestige_track.get_prestige() > 12:
            self.board.prestige_track.set_prestige(12)
          self.outputToHistory("US Prestige now %d" % self.board.prestige_track.get_prestige())
    else: # Muslim
      self.testCountry(where)
      woiRoll = self.getRollFromUser("Enter WoI roll or r to have program roll: ")
      modRoll = self.modifiedWoIRoll(woiRoll, where)
      self.outputToHistory("Modified Roll: %d" % modRoll)
      self.handleMuslimWoI(modRoll, where)

  def help_woi(self):
    print("Conduct War of Ideas operation.")

  def do_alert(self, rest):
    where = None
    while not where:
      input = self.getCountryFromUser("Alert in what country?  (? for list): ", "XXX", self.listPlotCountries)
      if input == "":
        print("")
        return
      else:
        if self.map[input].plots < 1:
          print("Country has not plots.")
          print("")
        else:
          where = input
    self.handleAlert(where)

  def help_alert(self):
    print("Alert an active Plot.")

  def do_reassessment(self, rest):
    self.handleReassessment()

  def help_reassessment(self):
    print("Reassessment of US Posture.")

  def do_regime(self, rest):
    if   self.map["United States"].soft_Q():
      print("No Regime Change with US Posture Soft")
      print("")
      return
    where = None
    while not where:
      input = self.getCountryFromUser("Regime Change in what country?  (? for list): ", "XXX", self.listIslamicCountries)
      if input == "":
        print("")
        return
      else:
        if (self.map[input].islamist_rule_Q()) or (input == "Iraq" and "Iraqi WMD" in self.markers) or (input == "Libya" and "Libyan WMD" in self.markers):
          where = input
        else:
          print("Country not Islamic Rule.")
          print("")
    moveFrom = None
    available = 0
    while not moveFrom:
      input = self.getCountryFromUser("Deploy 6+ troops from what country (track for Troop Track) (? for list)?: ",  "track", self.listCountriesWithTroops, 6)
      if input == "":
        print("")
        return
      elif input == "track":
        if self.board.troop_track.get_troops() <= 6:
          print("There are not enough troops on the Troop Track.")
          print("")
          return
        else:
          print("Deploy from Troop Track - %d available" % self.board.troop_track.get_troops())
          print("")
          available = self.board.troop_track.get_troops()
          moveFrom = input
      else:
        if self.map[input].troops() <= 6:
          print("There are not enough troops in %s." % input)
          print("")
          return
        else:
          print("Deploy from %s = %d availalbe" % (input, self.map[input].troops()))
          print("")
          available = self.map[input].troops()
          moveFrom = input
    howMany = 0
    while not howMany:
      input = self.getNumTroopsFromUser("Deploy how many troops (%d available)? " % available, available)
      if input == "":
        print("")
        return
      elif input < 6:
        print("At least 6 troops needed for Regime Change")
      else:
        howMany = input
    govRoll = self.getRollFromUser("Enter Governance roll or r to have program roll: ")
    preFirstRoll = self.getRollFromUser("Enter first die (Raise/Drop) for Prestige roll or r to have program roll: ")
    preSecondRoll = self.getRollFromUser("Enter second die for Prestige roll or r to have program roll: ")
    preThirdRoll = self.getRollFromUser("Enter thrid die for Prestige roll or r to have program roll: ")
    self.handleRegimeChange(where, moveFrom, howMany, govRoll, (preFirstRoll, preSecondRoll, preThirdRoll))

  def help_regime(self):
    print("Regime Change in Islamist Rule Country.")

  def can_withdraw_Q(self, rest) :
    return self.board.world['United States'].soft_Q()

  def do_withdraw(self, rest):
    if not can_withdraw_Q() :
      print("No Withdrawl with US Posture Hard\n")
      return

    moveFrom = None
    available = 0

    while not moveFrom:
      input = self.getCountryFromUser("Withdrawl in what country?  (? for list): ", "XXX", self.get_regime_change())
      if input == "":
        print("")
        return
      else:
        if self.board.world[input].regime_change_Q():
          moveFrom = input
          available = self.map[input].troops()
        else:
          print("Country not Regime Change.")
          print("")
    moveTo = None
    while not moveTo:
      input = self.getCountryFromUser("To what country (track for Troop Track)  (? for list)?: ",  "track", self.listDeployOptions)
      if input == "":
        print("")
        return
      elif input == "track":
        print("Withdraw troops from %s to Troop Track\n" % moveFrom)
        moveTo = input
      else:
        print("Withdraw troops from %s to %s\n" % (moveFrom, input))
        moveTo = input
    howMany = 0
    while not howMany:
      input = self.getNumTroopsFromUser("Withdraw how many troops (%d available)? " % available, available)
      if input == "":
        print("")
        return
      else:
        howMany = input
    preFirstRoll = self.getRollFromUser("Enter first die (Raise/Drop) for Prestige roll or r to have program roll: ")
    preSecondRoll = self.getRollFromUser("Enter second die for Prestige roll or r to have program roll: ")
    preThirdRoll = self.getRollFromUser("Enter thrid die for Prestige roll or r to have program roll: ")
    self.handleWithdraw(moveFrom, moveTo, howMany, (preFirstRoll, preSecondRoll, preThirdRoll))

  def help_withdraw(self):
    print("Withdraw Troops from Regime Change Country.")

  def do_j(self, rest):
    cardNum = None
    try:
      input = int(rest)
      if input < 1 or input > 120:
        print("Enter j then the card number e.g. j 24")
        print("")
        return
      else:
        cardNum = input
    except:
      print("Enter j then the card number e.g. j 24")
      print("")
      return
    self.SaveUndo()
    self.outputToHistory("", False)
    self.outputToHistory("== Jihadist plays %s - %d Ops ==" % (self.deck[str(cardNum)].name, self.deck[str(cardNum)].ops), True)

    self.aiFlowChartTop(cardNum)

  def help_j(self):
    print("Enter the number of the Jihadist card when it is their card play.")

  def do_u(self, rest):
    cardNum = None
    try:
      input = int(rest)
      if input < 1 or input > 120:
        print("Enter u then the card number e.g. u 24")
        print("")
        return
      else:
        cardNum = input
    except:
      print("Enter u then the card number e.g. u 24")
      print("")
      return
    self.SaveUndo()
    self.outputToHistory("", False)
    self.outputToHistory("== US plays %s - %d Ops ==" % (self.deck[str(cardNum)].name, self.deck[str(cardNum)].ops), True)


    if self.deck[str(cardNum)].playable("US", self):
      self.outputToHistory("Playable %s Event" % self.deck[str(cardNum)].type, False)
      if cardNum != 120:
        choice = self.getEventOrOpsFromUser("Play card for Event or Ops (enter e or o): ")
      else:
        choice = self.getEventOrOpsFromUser("This event must be played, do you want the Event or Ops to happen first (enter e or o): ")
      if choice == "event":
        self.outputToHistory("Played for Event.", False)
        self.deck[str(cardNum)].playEvent("US", self)
        if cardNum == 120:
          print("Now, %d Ops available. Use commands: alert, deploy, disrupt, reassessment, regime, withdraw, or woi" % self.deck[str(cardNum)].ops)
      elif choice == "ops":
        self.outputToHistory("Played for Ops.", False)
        if cardNum == 120:
          print("When finished with Ops enter u 120 again to play the event.")
        print("%d Ops available. Use commands: alert, deploy, disrupt, reassessment, regime, withdraw, or woi" % self.deck[str(cardNum)].ops)
    else:
      if self.deck[str(cardNum)].type == "Jihadist":
        if self.deck[str(cardNum)].playable("Jihadist", self):
          self.outputToHistory("Jihadist Event is playable.", False)
          playEventFirst = self.getYesNoFromUser("Do you want to play the Jihadist event before using the Ops? (y/n): ")
          if playEventFirst:
            self.deck[str(cardNum)].playEvent("Jihadist", self)
          else:
            print("Use the Ops now then enter u <card #> again to play the event")
          print("%d Ops available. Use commands: alert, deploy, disrupt, reassessment, regime, withdraw, or woi" % self.deck[str(cardNum)].ops)
          return
    # Here if it's unplayable by either side.
      self.outputToHistory("Unplayable %s Event" % self.deck[str(cardNum)].type, False)
      print("%d Ops available. Use commands: alert, deploy, disrupt, reassessment, regime, withdraw, or woi" % self.deck[str(cardNum)].ops)

  def help_u(self):
    print("Enter the number of the US card when it is your card play.")

  def do_plot(self, rest):
    foundPlot = False
    for country in self.map:
      while self.map[country].plots > 0:
        if not foundPlot:
          self.outputToHistory("", False)
          self.outputToHistory("[[ Resolving Plots ]]", True)
        foundPlot = True
        print("")
        plotType = self.getPlotTypeFromUser("Enter Plot type from %s: " % country)
        print("")
        isBacklash = False
        if self.backlashInPlay and (self.map[country].culture != 'Non-Muslim'):
          isBacklash = self.getYesNoFromUser("Was this plot selected with backlash (y/n): ")
        postureRoll = 0
        usPrestigeRolls = []
        schCountries = []
        schPostureRolls = []
        govRolls = []
        if country == "United States":
          if plotType != "WMD":
            postureRoll = random.randint(1,6)
            usPrestigeRolls.append(random.randint(1,6))
            usPrestigeRolls.append(random.randint(1,6))
            usPrestigeRolls.append(random.randint(1,6))
        elif self.map[country].culture != "Non-Muslim":
          if country != "Iran":
            numRolls = 0
            if plotType == "WMD":
              numRolls = 3
            else:
              numRolls = plotType
            for i in range(numRolls):
              govRolls.append(random.randint(1,6))
        elif self.map[country].non_muslim_Q():
          postureRoll = random.randint(1,6)
          if self.map[country].schengen:
            schChoices = []
            for cou in self.map:
              if cou != country and self.map[cou].schengen:
                schChoices.append(cou)
            schCountries.append(random.choice(schChoices))
            schCountries.append(schCountries[0])
            while schCountries[0] == schCountries[1]:
              schCountries[1] = random.choice(schChoices)
            for i in range(2):
              schPostureRolls.append(random.randint(1,6))
        self.resolvePlot(country, plotType, postureRoll, usPrestigeRolls, schCountries, schPostureRolls, govRolls, isBacklash)
    if not foundPlot:
      self.outputToHistory("", False)
      self.outputToHistory("[[ No unblocked plots to resolve ]]", True)
    self.backlashInPlay = False

  def help_plot(self):
    print("Use this command after the US Action Phase to resolve any unblocked plots.")

  def calculate_prestige(self) :
    vt = self.board.victory_track()
    mods = []
    if len(vt['islamist']) > 0 : 
      self.board.prestige_track.dec_prestige()
      mods.append("Islamist Rule")
    
    gwot = self.board.gwot()
    if gwot['world'] == self.board.world['United States'].posture.value and gwot['num'] == 3 :
      self.board.prestige_track.inc_prestige()
      mods.append("GWOT Strongly Aligned")
    return mods

  def do_turn(self, rest):
    self.SaveTurn()

    self.outputToHistory("\n* End of Turn.", False)
    if self.board.event_in_play_Q("Pirates") and (self.map["Somalia"].islamist_rule_Q() or self.map["Yemen"].islamist_rule_Q()):
      self.outputToHistory("No funding drop due to Pirates.", False)
    else:
      self.board.funding_track.dec_funding()
      self.outputToHistory("Jihadist Funding now %d\n" % self.board.funding_track.funding(), False)

    mods = self.calculate_prestige()
    self.outputToHistory("Prestige adjustments: %s => %d" % (mods, self.board.prestige_track.get_prestige()))

    self.outputToHistory("\n%s has Lapsed." % self.board.lapsing_events(), False)
    self.board.clear_lapsing_events()

    self.outputToHistory(self.board.tracker_summary())

    self.turn += 1
    self.outputToHistory("---\n", False)
    usCards = self.board.troop_track.draw_amount()
    jihadistCards = self.board.funding_track.draw_amount()

    self.outputToHistory("Jihadist draws %d cards." % jihadistCards, False)
    self.outputToHistory("US draws %d cards." % usCards, False)
    self.outputToHistory("---\n", False)
    self.outputToHistory("[[ %d (Turn %s) ]]\n" % (self.startYear + (self.turn - 1), self.turn), False)

  def help_turn(self):
    print("Use this command at the end of the turn.")

  def help_undo(self):
    print("Rolls back to last card played.")

  def do_undo(self, args):
    self.undo = self.getYesNoFromUser("Undo to last card played? (y/n): ")

  def help_quit(self):
    print("Quits game and prompt to save.")

  def do_quit(self, args):
    if self.getYesNoFromUser("Save? (y/n): "):
      print("Save suspend file.")
      self.Save(SUSPEND_FILE)

    print("Exiting.")


  def Save(self, fname):
    f = open(fname,'wb')
    pickle.dump("FIX SAVING",f,2)
    f.close()

  def SaveUndo(self):
    self.Save(UNDO_FILE)

  def SaveTurn(self):
    turnfile = ROLLBACK_FILE + str(self.turn) + ".lwot"
    self.Save(turnfile)

  def do_roll(self, args):
    self.do_rollback(args)

  def help_roll(self):
    self.help_rollback()

  def help_rollback(self):
    print("Roll back to any previous turn in the game.")

  def do_rollback(self, args):
    self.rollturn = -1
    needTurn = True
    while needTurn:
      try:
        lastturn = self.turn - 1
        input = raw_input("Rollback to which turn valid turns are 0 through " + str(lastturn) + "? Q to cancel rollback: " )

        if input == "Q":
          print("Cancel Rollback")
          break
        else:
          input = int(input)
          if input >= 0 and input <= lastturn:
            self.rollturn = input
            needTurn = False
          else:
            raise
      except:
        print("Entry error\n")

  def deploy(self, dst, num, src) :
    if src == 'troop_track' and self.board.troop_track.get_troops() < num :
      return (False, src, 'not_enough')
      
    if self.board.country(src).troops_stationed < num :
      return (False, src, 'not_enough')

    if src != 'troop_track' and self.board.country(src).regime_change_Q() :
      c = self.board.country(src)
      if (c.troops_stationed - num) < (c.totalCells(True) + 5) :
        return (False, src, 'regime_change_troop_restriction')

    if dst != 'troop_track' and self.board.country(dst) not in self.board.get_allied_countries() :
      return (False, dst, 'not_allied')

    x, t = self.board.place_troops(dst, num, src)
    if t != num : raise Exception("units moved is different")
    return (True, dst, num, src)

def getUserYesNoResponse(prompt):
  good = None
  while not good:
    try:
      input = raw_input(prompt)
      if input.lower() == "y" or input.lower() == "yes":
        return True
      elif input.lower() == "n" or input.lower() == "no":
        return False
      else:
        print("Enter y or n.")
        print("")
    except:
      print("Enter y or n.")
      print("")

def raw_input(prompt):
  return input(prompt)

class UICmd(cmd.Cmd) :
  class GameState(Enum) :
    MAIN_MENU = "Main Menu"
    GAME = "LWOT"

  def __init__(self) :
    cmd.Cmd.__init__(self)
    self.prompt_temp = "%d Turn (%d): "
    self.state = UICmd.GameState.MAIN_MENU
    self.prompt = self.state.value
    self.game = None

    scenario_config = None
    with open(SCENARIOS_FILE, 'r') as f:
      scenario_config = yaml.load(f)

    self.scenario_opts = list(scenario_config.keys())

  def clear_screen(self) : os.system('cls' if os.name == 'nt' else 'clear') 

  def main_menu(self) :
    self.clear_screen()

    m_str = "\nWelcome to Labyrinth (Main Menu)\n"
    m_str += "   0 -> quit game"

    for opt in self.scenario_opts :
      m_str += "\n   %d -> %s" % (self.scenario_opts.index(opt) + 1, opt.replace('_', ' ').title())
    
    print(m_str)
    self.prompt = "\nSelect scenario: "

  def default(self, line) :
    if self.state == self.GameState.MAIN_MENU :
      if line.isdigit() :
        opt = int(line)
        if opt == 0 : return True
        elif opt > 0 and opt <= len(self.scenario_opts) :
          self.clear_screen()
          print("\n" + self.scenario_opts[opt - 1].replace('_', ' ').title())
          print("Jihadist Ideology: Normal\n")
          self.game = Labyrinth(self.scenario_opts[opt - 1], 1)
          print(self.game.board)
          self.state = self.GameState.GAME
          return False

      self.main_menu()
          
    elif self.state == self.GameState.GAME :
      raise Exception("Unknown Command!")

  def preloop(self) :
    self.main_menu()

#  def precmd(self, line) :
    
  def postcmd(self, stop, line) :
    if self.state == self.GameState.MAIN_MENU :
      return stop      
    elif self.state == self.GameState.GAME :
      self.prompt = self.prompt_temp % (self.game.startYear + self.game.turn - 1, self.game.turn)

    return stop

  def do_status(self, args) :
    if len(args) == 0 :
      print(self.game.board)
    else :
      print(self.game.board.country_summary(args))

  def complete_status(self, text, line, begidx, endidx) :
    return [ c for c in list(self.game.board.world.keys()) if c.startswith(text) ]

  def help_status(self):
    print("    Display status of game or single country")
    print("    Usage: status OR status <country>\n")

  def parse_deploy(self, line, params) :
    m = re.match('deploy ([a-zA-Z/]+( [a-zA-Z]+)?) ([0-9]+) ([a-zA-Z/]+( [a-zA-Z]+)?)$'
    if m == None : return False

    params['dst'] = m.group(1)
    params['num'] = int(m.group(3))
    params['src'] = m.group(4)

    return False

  def do_deploy(self, line):
    args = {}

    if not self.parse_deploy(line, args) :
      print("Unknown usage\n")
      self.help_deploy()
      return False

    res = self.game.deploy(args['dst'], args['num'], args['src'])
    if res[0] == True : 
      print("   Deployed to %s, %d troops, from %s" % (args['dst'], args['num'], args['src']))
      return False

    if res[0] == False and res[2] == 'not_enough':
      print("   Not enough troops in %s (%d) to deploy" % (src, self.board.country(src).troops_stationed)) 
      return False

    if res[0] == False and res[2] == 'regime_change_troop_restriction' :
      print("   Not enough troops in %s (%d) to deploy [7.3.1]")
      return False

    if res[0] == False and res[2] == 'not_allied':
      print("   Can not deploy to %s (%s)" % (args['dst'], self.game.board.country(args['dst']).alignment.name))
      return False

  def complete_deploy(self, text, line, begidx, endidx) :
    if re.match("deploy $", line) != None and len(text) <= 0 :
      allied = self.game.board.get_allied_countries()
      if len(allied) == 1 : return [ allied[0].name ]
      return [ "%s (%d)" % (c.name, c.troops()) for c in allied]
    elif re.match('deploy ([a-zA-Z/]+)$', line) != None:
      allied = self.game.board.get_allied_countries()
      if len(allied) == 1 : return [ allied[0].name ]
      return [ c.name for c in allied if c.name.startswith(text) ]
    elif re.match('deploy ([a-zA-Z/]+( [a-zA-Z]+)?) $', line) != None:
      tc = self.game.board.get_troops_countries()
      if len(tc) == 1 : return [ tc[0].troops_stationed ]
      return ([ "%s (%d)" % (c.name, c.troops()) for c in tc ])
    elif re.match('deploy ([a-zA-Z/]+( [a-zA-Z]+)?) ([0-9]+) $', line) != None:
      m = re.match('deploy ([a-zA-Z/]+( [a-zA-Z]+)?) ([0-9]+) $', line)
      t = int(m.group(3))
      tc = [ c for c in self.game.board.get_troops_countries() if c.troops_stationed >= t ]
      if len(tc) == 1 and tc[0].troops_stationed >= t : return [ tc[0].name ]
      return ([ "%s (%d)" % (c.name, c.troops()) for c in tc ])
    else : return []
    

  def help_deploy(self):
    print("   US Action: Deploy - 7.3")
    print("   Usage: deploy <to country> <num of troops> <from country>\n")

  def do_quit(self, args) : return True

#  def do_withdraw(self, args) :

def main():

  print("\nLabyrinth: The War on Terror AI Player\n")
  scenario = 0
  ideology = 0
  loadfile = 0

  # Starting new session unlink undo save
  if os.path.exists(UNDO_FILE):
    os.remove(UNDO_FILE)

  # Starting new session unlink previous turn saves
  for each in os.listdir(os.curdir):
    if "turn." in each and ".lwot" in each:
      os.remove(each)

  # Ask user if they want to continue previous game
  if os.path.exists(SUSPEND_FILE):
    res = getUserYesNoResponse("Resume suspended game? (y/n): ")
    if res:
      loadfile = 1


  if loadfile == 0:
    while scenario == 0:
      try:
        print("Choose Scenario")
        print("(1) Let's Roll!")
        print("(2) You Can Call Me Al")
        print("(3) Anaconda")
        print("(4) Mission Accomplished?")
        input = raw_input("Enter choice: ")
        input = int(input)
        if input >= 1 and input <= 5:
          scenario = input
          print("")
        else:
          raise
      except:
        print("Entry error\n")

    while ideology == 0:
      try:
        print("Choose Jihadist Ideology")
        print("(1) Normal")
        print("(2) Attractive (2 cells per recruit success)")
        print("(3) Potent (+ Only 3 more cells than troops needed for Major Jihad)")
        print("(4) Infectious (+ No program impact - US must remember to play all your cards)")
        print("(5) Virulent (+ Failed Jihad rolls do not remove cells)")
        input = raw_input("Enter choice: ")
        input = int(input)
        if input >= 1 and input <= 5:
          ideology = input
          print("")
        else:
          raise
      except:
        print("Entry error\n")

    app = Labyrinth(scenario, ideology)
    turnfile = ROLLBACK_FILE + "0.lwot"
    app.Save(turnfile)

  else:
    # Load previous game save
    f = open(SUSPEND_FILE,'rb')
    app = pickle.load(f)
    app.stdout = sys.stdout
    f.close()


  rollback = True
  while rollback == True:

    app.cmdloop()

    # exit out of cmdloop when user quits, want to undo, or rollback - prevents issues dealing with save/reloading within class instance
    if app.undo:
      print("Undo to last turn")
      f = open(UNDO_FILE,'rb')

      app = pickle.load(f)
      app.stdout = sys.stdout

      f.close()
    elif app.rollturn >= 0:
      print("Rolling back to turn " + str(app.rollturn))
      turnfile = ROLLBACK_FILE + str(app.rollturn) + '.lwot'
      f = open(turnfile,'rb')

      app = pickle.load(f)
      app.stdout = sys.stdout

      f.close()
      # rollback invalidates undo save so delete it
      if os.path.exists(UNDO_FILE):
        os.remove(UNDO_FILE)

    else:
      rollback = False




if __name__ == "__main__":
  UICmd().cmdloop()
  #main()
