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

import sys
import cmd
import random
import shutil
try:
  import cPickle as pickle
except:
  import pickle
import os.path
import yaml
from enum import IntEnum

class Governance(IntEnum):
  ISLAMIST_RULE = 4
  POOR = 3
  FAIR = 2
  GOOD = 1

class Alignment(IntEnum):
  ADVERSARY = 1
  NEUTRAL = 2
  ALLY = 3

COUNTRY_STATS = {'governance': Governance, 'alignment': Alignment}

class Country:
  app = None
  name = ""
  type = ""
  posture = ""
  alignment = ""
  governance = 0
  schengen = False
  recruit = 0
  troops_stationed = 0
  activeCells = 0
  sleeper_cells = 0
  oil = False
  resources = 0
  links = []
  markers = []
  schengenLink = False
  aid = 0
  besiged = 0
  regimeChange = 0
  cadre = 0
  plots = 0

  def __init__(self, theApp, theName, theType, thePosture, theAlignment, theGovernance, theSchengen, theRecruit, no1,no2,no3, theOil, theResources):
    self.app = theApp
    self.name = theName
    self.type = theType
    self.posture = thePosture
    self.alignment = theAlignment
    self.governance = theGovernance
    self.schengen = theSchengen
    self.recruit = theRecruit
    self.troops_stationed = 0
    self.activeCells = 0
    self.sleeper_cells = 0
    self.oil = theOil
    self.resources = theResources
    self.aid = 0
    self.besieged = 0
    self.regimeChange = 0
    self.cadre = 0
    self.plots = 0
    self.links = []
    self.markers = []
    self.schengenLink = False

  def totalCells(self, includeSadr = False):
    total = self.activeCells + self.sleeper_cells
    if includeSadr and "Sadr" in self.markers:
      total += 1
    return total

  def numActiveCells(self):
    total = self.activeCells
    if "Sadr" in self.markers:
      total += 1
    return total

  def removeActiveCell(self):
    self.activeCells -= 1
    if self.activeCells < 0:
      if "Sadr" in self.markers:
        self.markers.remove("Sadr")
        self.app.outputToHistory("Sadr removed from %s" % self.name, False)
        return
      else:
        self.activeCells = 0
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
    if self.governance == 1:
      return "Good"
    elif self.governance == 2:
      return "Fair"
    elif self.governance == 3:
      return "Poor"
    elif self.governance == 4:
      return "Islamic Rule"

  def typePretty(self, theType):
    if theType == "Non-Muslim":
      return "NM"
    elif theType == "Suni":
      return "SU"
    elif theType == "Shia-Mix":
      return "SM"
    else:
      return "IR"

  def countryStr(self):
    markersStr = ""
    if len(self.markers) != 0:
      markersStr = "\n   Markers: %s" % ", ".join(self.markers)
    if self.type == "Shia-Mix" or self.type == "Suni":
      return "%s, %s %s, %d Resource(s)\n   Troops:%d Active:%d Sleeper:%d Cadre:%d Aid:%d Besieged:%d Reg Ch:%d Plots:%d %s" % (self.name, self.govStr(),self.alignment,self.app.countryResources(self.name),self.troops(),self.activeCells,self.sleeper_cells, self.cadre, self.aid, self.besieged, self.regimeChange, self.plots, markersStr)

    elif self.name == "Philippines":
      return "%s - Posture:%s\n   Troops:%d Active:%d Sleeper:%d Cadre:%d Plots:%d %s" % (self.name,self.posture, self.troops(), self.activeCells,self.sleeper_cells, self.cadre, self.plots, markersStr)


    elif self.type == "Non-Muslim" and self.type != "United States":
      return "%s - Posture:%s\n   Active:%d Sleeper:%d Cadre:%d Plots:%d %s" % (self.name,self.posture, self.activeCells,self.sleeper_cells, self.cadre, self.plots, markersStr)
    elif self.type == "Iran":
      return "%s, %s\n   Active:%d Sleeper:%d Cadre:%d Plots:%d %s" % (self.name, self.govStr(),self.activeCells,self.sleeper_cells, self.cadre, self.plots, markersStr)

  def printCountry(self):
    print(self.countryStr())

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
          if (app.map[country].type != "Non-Muslim") and (app.map[country].plots > 0):
            return True
        return False
      elif self.number == 2: # Biometrics
        return True
      elif self.number == 3: # CRT
        return app.map["United States"].posture == "Soft"
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
        return (app.map["Somalia"].governance == 4) or (app.map["Sudan"].governance == 4)
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
            if app.map[country].alignment == "Ally" or app.map[country].governance == 1:
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
            if app.map[country].type == "Suni" or app.map[country].type == "Shia-Mix":
              numMuslimCellCountries += 1
        return numMuslimCellCountries > 0
      elif self.number == 26: # Quartet
        if not "Abbas" in app.markers:
          return False
        if app.troops <= 4:
          return False
        for country in app.map:
          if app.isAdjacent(country, "Israel"):
            if app.map[country].governance == 4:
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
          if app.map[country].totalCells() > 0 or app.map[country].cadre > 0 or app.map[country].plots > 0:
            return True
        return False
      elif self.number == 32: # Back Channel
        if app.map["United States"].posture == "Hard":
          return False
        numAdv = app.numAdversary()
        if numAdv <= 0:
          return False
        app.listAdversaryCountries()
        return app.getYesNoFromUser("Do you have a card with a value that exactly matches an Adversary's Resources? (y/n): ")
      elif self.number == 33: # Benazir Bhutto
        if "Bhutto Shot" in app.markers:
          return False
        if app.map["Pakistan"].governance == 4:
          return False
        for countryObj in app.map["Pakistan"].links:
          if countryObj.governance == 4:
            return False
        return True
      elif self.number == 34: # Enhanced Measures
        if "Leak-Enhanced Measures" in app.markers or app.map["United States"].posture == "Soft":
          return False
        return app.numDisruptable() > 0
      elif self.number == 35: # Hajib
        return app.numIslamicRule() == 0
      elif self.number == 36: # Indo-Pakistani Talks
        if app.map['Pakistan'].governance == 1 or app.map['Pakistan'].governance == 2:
          return True
        return False
      elif self.number == 37: # Iraqi WMD
        if app.map["United States"].posture == "Hard" and app.map["Iraq"].alignment == "Adversary":
          return True
        return False
      elif self.number == 38: # Libyan Deal
        if app.map["Libya"].governance == 3:
          if app.map["Iraq"].alignment == "Ally" or app.map["Syria"].alignment == "Ally":
            return True
        return False
      elif self.number == 39: # Libyan WMD
        if app.map["United States"].posture == "Hard" and app.map["Libya"].alignment == "Adversary" and "Libyan Deal" not in app.markers:
          return True
        return False
      elif self.number == 40: # Mass Turnout
        return app.numRegimeChange() > 0
      elif self.number == 41: # NATO
        return (app.numRegimeChange() > 0) and (app.gwotPenalty() >= 0)
      elif self.number == 42: # Pakistani Offensive
        return (app.map["Pakistan"].alignment == "Ally") and ("FATA" in app.map["Pakistan"].markers)
      elif self.number == 43: # Patriot Act
        return True
      elif self.number == 44: # Renditions
        return (app.map["United States"].posture == "Hard") and ("Leak-Renditions" not in app.markers)
      elif self.number == 45: # Safer Now
        if app.numIslamicRule() > 0:
          return False
        for country in app.map:
          if app.map[country].governance == 1:
            if app.map[country].totalCells(True) > 0 or app.map[country].plots > 0:
              return False
        return True
      elif self.number == 46: # Sistani
        targetCountries = 0
        for country in app.map:
          if app.map[country].type == "Shia-Mix":
            if app.map[country].regimeChange > 0:
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
          if app.map[country].regimeChange > 0:
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
          if app.map[country].regimeChange > 0 and app.map[country].totalCells() > 0:
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
        return app.map["Somalia"].governance == 4 or app.map["Yemen"].governance == 4
      elif self.number == 74: # Schengen Visas
        return True
      elif self.number == 75: # Schroeder & Chirac
        return app.map["United States"].posture == "Hard"
      elif self.number == 76: # Abu Ghurayb
        targetCountries = 0
        for country in app.map:
          if app.map[country].regimeChange > 0:
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
          if app.map[country].regimeChange > 0:
            if app.map[country].totalCells(True) > 0:
              return True
        return False
      elif self.number == 91: # Regional al-Qaeda
        num = 0
        for country in app.map:
          if app.map[country].type == "Suni" or app.map[country].type == "Shia-Mix":
            if app.map[country].governance == 0:
              num += 1
        return num >= 2
      elif self.number == 92: # Saddam
        if "Saddam Captured" in app.markers:
          return False
        return (app.map["Iraq"].governance == 3) and (app.map["Iraq"].alignment == "Adversary")
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
          if app.map[country].type == "Shia-Mix":
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
          if app.map[country].regimeChange > 0:
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
            if app.map[country].type == "Non-Muslim":
              if app.map[country].posture == "Hard":
                return True
            else:
              if app.map[country].alignment == "Ally":
                return True
      elif self.number == 116: # KSM
        if side == "US":
          for country in app.map:
            if app.map[country].plots > 0:
              if app.map[country].type == "Non-Muslim" or app.map[country].alignment == "Ally":
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
          if (app.map[country].type != "Non-Muslim") and (app.map[country].plots > 0):
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
        if (app.map["Central Asia"].alignment == "Ally") or (app.map["Central Asia"].alignment == "Neutral"):
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
              print("There are no cells in %s" % input)
              print("")
            else:
              foundTroops = False
              for country in app.map:
                if country == input or app.isAdjacent(input, country):
                  if app.map[country].troops() > 0:
                    foundTroops = True
                    break
              if not foundTroops:
                print("Neither this or any adjacent country have troops.")
                print("")
              else:
                app.removeCell(input)
                app.outputToHistory(app.map[input].countryStr(), True)
                break
      elif self.number == 11: # Abbas
        numIRIsrael = 0
        for country in app.map:
          if app.isAdjacent(country, "Israel"):
            if app.map[country].governance == 4:
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
                print("%s is not an Adversary." % input)
                print("")
              else:
                targetCountry = input
                break
        actionRoll = app.getRollFromUser("Enter Covert Action roll or r to have program roll: ")
        if actionRoll >= 4:
          app.map[targetCountry].alignment = "Neutral"
          app.outputToHistory("Covert Action successful, %s now Neutral." % targetCountry, False)
          app.outputToHistory(app.map[input].countryStr(), True)
        else:
          app.outputToHistory("Covert Action fails.", True)
      elif self.number == 15: # Ethiopia Strikes
        if (app.map["Somalia"].governance == 4) or (app.map["Sudan"].governance == 4):
          if app.map["Somalia"].governance != 4:
            app.map["Sudan"].governance = 3
            app.map["Sudan"].alignment = "Neutral"
            app.outputToHistory("Sudan now Poor Neutral.", False)
            app.outputToHistory(app.map["Sudan"].countryStr(), True)
          elif app.map["Sudan"].governance != 4:
            app.map["Somalia"].governance = 3
            app.map["Somalia"].alignment = "Neutral"
            app.outputToHistory("Somalia now Poor Neutral.", False)
            app.outputToHistory(app.map["Somalia"].countryStr(), True)
          else:
            print("Both Somalia and Sudan are under Islamic Rule.")
            if app.getYesNoFromUser("Do you want Somalia to be set to Poor Neutral? (y/n): "):
              app.map["Somalia"].governance = 3
              app.map["Somalia"].alignment = "Neutral"
              app.outputToHistory("Somalia now Poor Neutral.", False)
              app.outputToHistory(app.map["Somalia"].countryStr(), True)
            else:
              app.map["Sudan"].governance = 3
              app.map["Sudan"].alignment = "Neutral"
              app.outputToHistory("Sudan now Poor Neutral.", False)
              app.outputToHistory(app.map["Sudan"].countryStr(), True)
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
              app.outputToHistory(app.map["Central Asia"].countryStr(), True)
            elif cenAsiaCells == 0:
              app.removeCell("Russia")
              app.outputToHistory(app.map["Russia"].countryStr(), True)
            else:
              isRussia = app.getYesNoFromUser("There are cells in both Russia and Central Asia. Do you want to remove a cell in Russia? (y/n): ")
              if isRussia:
                app.removeCell("Russia")
                app.outputToHistory(app.map["Russia"].countryStr(), True)
              else:
                app.removeCell("Central Asia")
                app.outputToHistory(app.map["Central Asia"].countryStr(), False)
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
        app.outputToHistory(app.map["Turkey"].countryStr(), True)
      elif self.number == 20: # King Abdullah
        app.outputToHistory("Jordan now a Fair Ally.", False)
        app.map["Jordan"].governance = 2
        app.map["Jordan"].alignment = "Ally"
        app.outputToHistory(app.map["Jordan"].countryStr(), True)
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
            elif app.map[input].type == "Iran":
              print("Iran is not allowed.")
              print("")
            elif app.map[input].type == "Non-Muslim":
              print("Choose a Muslim country.")
              print("")
            else:
              app.removeCell(input)
              app.outputToHistory(app.map[input].countryStr(), True)
              break
      elif self.number == 26: # Quartet
        if not "Abbas" in app.markers:
          return False
        if app.troops <= 4:
          return False
        for country in app.map:
          if app.isAdjacent(country, "Israel"):
            if app.map[country].governance == 4:
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
        app.outputToHistory(app.map["Iraq"].countryStr(), True)
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
        app.outputToHistory(app.map[target].countryStr(), True)
      elif self.number == 29: # Tony Blair
        app.map["United Kingdom"].posture = app.map["United States"].posture
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
            if app.map[country].regimeChange > 0:
              target = country
              break
        else:
          while True:
            input = app.getCountryFromUser("Choose a Regime Change country (? for list): ",  "XXX", app.listRegimeChangeCountries)
            if input == "":
              print("")
              return
            else:
              if app.map[input].regimeChange <= 0:
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
          if app.map[country].activeCells > 0:
            num = app.map[country].activeCells
            if num > 0:
              app.map[country].activeCells -= num
              app.cells += num
              app.outputToHistory("%d Active Cell(s) removed from %s." % (num, country), False)
          if app.map[country].sleeper_cells > 0:
            num = app.map[country].sleeper_cells
            if num > 0:
              app.map[country].sleeper_cells -= num
              app.cells += num
              app.outputToHistory("%d Sleeper Cell(s) removed from %s." % (num, country), False)
          if app.map[country].cadre > 0:
            num = app.map[country].cadre
            if num > 0:
              app.map[country].cadre = 0
              app.outputToHistory("Cadre removed from %s." % country, False)
          if app.map[country].plots > 0:
            num = app.map[country].plots
            if num > 0:
              app.map[country].plots -= num
              app.outputToHistory("%d Plots remove(d) from %s." % (num, country), False)
        app.markers.append("Wiretapping")
        app.outputToHistory("Wiretapping in Play.", True)
      elif self.number == 32: # Back Channel
        if app.map["United States"].posture == "Hard":
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
                app.outputToHistory(app.map[input].countryStr(), True)
                break
      elif self.number == 33: # Benazir Bhutto
        app.markers.append("Benazir Bhutto")
        app.outputToHistory("Benazir Bhutto in Play.", False)
        if app.map["Pakistan"].governance == 3:
          app.map["Pakistan"].governance = 2
          app.outputToHistory("Pakistan now Fair governance.", False)
        app.outputToHistory("No Jihads in Pakistan.", False)
        app.outputToHistory(app.map["Pakistan"].countryStr(), True)
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
        app.map["France"].posture = posStr
        app.outputToHistory(app.map["Turkey"].countryStr(), False)
        app.outputToHistory(app.map["France"].countryStr(), True)
      elif self.number == 36: # Indo-Pakistani Talks
        app.markers.append("Indo-Pakistani Talks")
        app.outputToHistory("Indo-Pakistani Talks in Play.", False)
        app.map['Pakistan'].alignment = "Ally"
        app.outputToHistory("Pakistan now Ally", False)
        posStr = app.getPostureFromUser("Select India's Posture (hard or soft): ")
        app.map["India"].posture = posStr
        app.outputToHistory(app.map["Pakistan"].countryStr(), False)
        app.outputToHistory(app.map["India"].countryStr(), True)
      elif self.number == 37: # Iraqi WMD
        app.markers.append("Iraqi WMD")
        app.outputToHistory("Iraqi WMD in Play.", False)
        app.outputToHistory("Use this or a later card for Regime Change in Iraq at any Governance.", True)
      elif self.number == 38: # Libyan Deal
        app.markers.append("Libyan Deal")
        app.outputToHistory("Libyan Deal in Play.", False)
        app.map["Libya"].alignment == "Ally"
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
                app.map[target].posture = posStr
                app.outputToHistory(app.map[target].countryStr(), False)
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
            if app.map[country].regimeChange > 0:
              target = country
              break
        else:
          while True:
            input = app.getCountryFromUser("Choose a Regime Change Country to improve governance (? for list): ",  "XXX", app.listRegimeChangeCountries)
            if input == "":
              print("")
              return
            else:
              if app.map[input].regimeChange <= 0:
                print("%s is not a Regime Change country." % input)
                print("")
              else:
                target = input
                break
        app.improveGovernance(target)
        app.outputToHistory("%s Governance improved." % target, False)
        app.outputToHistory(app.map[target].countryStr(), True)
      elif self.number == 41: # NATO
        numRC = app.numRegimeChange()
        target = ""
        if numRC <= 0:
          return False
        elif numRC == 1:
          for country in app.map:
            if app.map[country].regimeChange > 0:
              target = country
              break
        else:
          while True:
            input = app.getCountryFromUser("Choose a Regime Change Country to land NATO troops (? for list): ",  "XXX", app.listRegimeChangeCountries)
            if input == "":
              print("")
              return
            else:
              if app.map[input].regimeChange <= 0:
                print("%s is not a Regime Change country." % input)
                print("")
              else:
                target = input
                break
        app.map[target].markers.append("NATO")
        app.outputToHistory("NATO added in %s" % target, False)
        app.map[target].aid = 1
        app.outputToHistory("Aid added in %s" % target, False)
        app.outputToHistory(app.map[target].countryStr(), True)
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
          app.map["United States"].posture = "Soft"
          app.outputToHistory("US Posture now Soft.", False)
        else:
          app.map["United States"].posture = "Hard"
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
              app.map[postureCountry].posture = postureStr
              app.outputToHistory(app.map["United States"].countryStr(), False)
              app.outputToHistory(app.map[postureCountry].countryStr(), True)
              break
      elif self.number == 46: # Sistani
        targetCountries = []
        for country in app.map:
          if app.map[country].type == "Shia-Mix":
            if app.map[country].regimeChange > 0:
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
        app.outputToHistory(app.map[target].countryStr(), True)
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
          if app.map["China"].posture == "Soft":
            app.map["China"].sleeper_cells += 1
            app.cells -= 1
            app.outputToHistory("Sleeper Cell placed in China", False)
            app.outputToHistory(app.map["China"].countryStr(), True)
          else:
            app.testCountry("Central Asia")
            app.map["Central Asia"].sleeper_cells += 1
            app.cells -= 1
            app.outputToHistory("Sleeper Cell placed in Central Asia", False)
            app.outputToHistory(app.map["Central Asia"].countryStr(), True)
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
          app.outputToHistory(app.map[target].countryStr(), True)
        app.outputToHistory("Draw a card for the Jihadist and put it on the top of their hand.", True)
      elif self.number == 62: # Ex-KGB
        if "CTR" in app.map["Russia"].markers:
          app.map["Russia"].markers.remove("CTR")
          app.outputToHistory("CTR removed from Russia.", True)
        else:
          targetCaucasus = False
          if app.map["Caucasus"].posture == "" or app.map["Caucasus"].posture == app.map["United States"].posture:
            if app.gwotPenalty() == 0:
              cacPosture = app.map["Caucasus"].posture
              if app.map["United States"].posture == "Hard":
                app.map["Caucasus"].posture = "Soft"
              else:
                app.map["Caucasus"].posture = "Hard"
              if app.gwotPenalty() < 0:
                targetCaucasus = True
              app.map["Caucasus"].posture = cacPosture
          if targetCaucasus:
            if app.map["United States"].posture == "Hard":
              app.map["Caucasus"].posture = "Soft"
            else:
              app.map["Caucasus"].posture = "Hard"
            app.outputToHistory("Caucasus posture now %s" % app.map["Caucasus"].posture, False)
            app.outputToHistory(app.map["Caucasus"].countryStr(), True)
          else:
            app.testCountry("Central Asia")
            if app.map["Central Asia"].alignment == "Ally":
              app.map["Central Asia"].alignment = "Neutral"
              app.outputToHistory("Central Asia now Neutral.", True)
            elif app.map["Central Asia"].alignment == "Neutral":
              app.map["Central Asia"].alignment = "Adversary"
              app.outputToHistory("Central Asia now Adversary.", True)
            app.outputToHistory(app.map["Central Asia"].countryStr(), True)
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
          app.outputToHistory(app.map["Syria"].countryStr(), True)
        app.outputToHistory(app.map["Lebanon"].countryStr(), True)
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
        if app.map["Afghanistan"].governance == 4:
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
        app.map["Germany"].posture = "Soft"
        app.outputToHistory("%s Posture now %s" % ("Germany", app.map["Germany"].posture), True)
        app.map["France"].posture = "Soft"
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
          if app.map[target].alignment == "Ally":
            app.map[target].alignment = "Neutral"
          elif app.map[target].alignment == "Neutral":
            app.map[target].alignment = "Adversary"
          app.outputToHistory("%s Alignment shifted to %s." % (target, app.map[target].alignment), True)
      elif self.number == 78: # Axis of Evil
        app.outputToHistory("US discards any Iran, Hizballah, or Jaysh al-Mahdi cards from hand.", False)
        if app.map["United States"].posture == "Soft":
          app.map["United States"].posture = "Hard"
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
          if app.map[country].regimeChange > 0:
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
        app.outputToHistory(app.map[target].countryStr(), True)
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
        if app.map["Pakistan"].alignment == "Ally":
          app.map["Pakistan"].alignment = "Neutral"
        elif app.map["Pakistan"].alignment == "Neutral":
          app.map["Pakistan"].alignment = "Adversary"
        app.outputToHistory("%s Alignment shifted to %s." % ("Pakistan", app.map["Pakistan"].alignment), True)
        app.outputToHistory(app.map["Pakistan"].countryStr(), True)
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
          app.map["United States"].posture = "Soft"
        else:
          app.map["United States"].posture = "Hard"
        app.outputToHistory("US Posture now %s" % app.map["United States"].posture, True)
      elif self.number == 86: # Lebanon War
        app.outputToHistory("US discards a random card.", False)
        app.changePrestige(-1, False)
        possibles = []
        for country in app.map:
          if app.map[country].type == "Shia-Mix":
            possibles.append(country)
        target = random.choice(possibles)
        app.placeCells(target, 1)
      elif self.number == 87 or self.number == 88 or self.number == 89: # Martyrdom Operation
        if app.executePlot(1, False, [1], True) == 1:
          app.outputToHistory("No plots could be placed.", True)
          app.handleRadicalization(app.deck[str(self.number)].ops)
      elif self.number == 90: # Quagmire
        app.map["United States"].posture = "Soft"
        app.outputToHistory("US Posture now Soft.", False)
        app.outputToHistory("US randomly discards two cards and Jihadist plays them.", False)
        app.outputToHistory("Do this using the j # command for each card.", True)
      elif self.number == 91: # Regional al-Qaeda
        possibles = []
        for country in app.map:
          if app.map[country].type == "Suni" or app.map[country].type == "Shia-Mix":
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
        if (app.map["Afghanistan"].governance == 4) or (app.map["Pakistan"].governance == 4):
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
        app.outputToHistory(app.map[target].countryStr(), True)
      elif self.number == 95: # Wahhabism
        if app.map["Saudi Arabia"].governance == 4:
          app.changeFunding(9)
        else:
          app.changeFunding(app.map["Saudi Arabia"].governance)
    else:
      if self.number == 96: # Danish Cartoons
        posStr = app.getPostureFromUser("Select Scandinavia's Posture (hard or soft): ")
        app.map["Scandinavia"].posture = posStr
        app.outputToHistory("Scandinavia posture now %s." % posStr, False)
        possibles = []
        for country in app.map:
          if app.map[country].type == "Suni" or app.map[country].type == "Shia-Mix":
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
        if app.map["United States"].posture == "Soft":
          app.map["Serbia"].posture = "Hard"
        else:
          app.map["Serbia"].posture = "Soft"
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
            if country not in possibles and app.map[country].totalCells(True) > 0 and app.map[country].type == "Shia-Mix":
              possibles.append(country)
          for country in twoAway:
            if country not in possibles and app.map[country].totalCells(True) > 0 and app.map[country].type == "Shia-Mix":
              possibles.append(country)
          for country in threeAway:
            if country not in possibles and app.map[country].totalCells(True) > 0 and app.map[country].type == "Shia-Mix":
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
            app.outputToHistory(app.map[target].countryStr(), True)
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
              if app.map[input].type != "Shia-Mix":
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
          app.outputToHistory(app.map[target].countryStr(), True)
        else:
          possibles = []
          for country in app.map:
            if app.map[country].type == "Shia-Mix":
              possibles.append(country)
          target = random.choice(possibles)
          app.testCountry(target)
          tested = target
          target = None
          goods = []
          for country in app.map:
            if app.map[country].type == "Shia-Mix" or app.map[country].type == "Suni":
              if app.map[country].governance == 1:
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
              if app.map[country].type == "Shia-Mix" or app.map[country].type == "Suni":
                if app.map[country].governance == 2:
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
                app.outputToHistory(app.map[target].countryStr(), True)
            else:
              app.outputToHistory("Roll failed.  No change to governance in %s." % target, False)

      elif self.number == 106: # Jaysh al-Mahdi
        if side == "US":
          target = None
          possibles = []
          for country in app.map:
            if app.map[country].type == "Shia-Mix":
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
          app.outputToHistory(app.map[target].countryStr(), True)
        else:
          possibles = []
          for country in app.map:
            if app.map[country].type == "Shia-Mix":
              possibles.append(country)
          target = random.choice(possibles)
          app.testCountry(target)
          tested = target
          target = None
          goods = []
          for country in app.map:
            if app.map[country].type == "Shia-Mix" or app.map[country].type == "Suni":
              if app.map[country].governance == 1:
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
              if app.map[country].type == "Shia-Mix" or app.map[country].type == "Suni":
                if app.map[country].governance == 2:
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
              app.outputToHistory(app.map[target].countryStr(), True)
      elif self.number == 107: # Kurdistan
        if side == "US":
          app.testCountry("Iraq")
          app.map["Iraq"].aid = 1
          app.outputToHistory("Aid added to Iraq.", False)
          app.outputToHistory(app.map["Iraq"].countryStr(), True)
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
          app.outputToHistory(app.map[target].countryStr(), True)
      elif self.number == 108: # Musharraf
        app.removeCell("Pakistan")
        app.map["Pakistan"].governance = 3
        app.map["Pakistan"].alignment = "Ally"
        app.outputToHistory("Pakistan now Poor Ally.", False)
        app.outputToHistory(app.map["Pakistan"].countryStr(), True)
      elif self.number == 109: # Tora Bora
        possibles = []
        for country in app.map:
          if app.map[country].regimeChange > 0:
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
          app.outputToHistory(app.map[target].countryStr(), True)
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
          if app.map["Sudan"].alignment == "Ally":
            app.map["Sudan"].alignment = "Neutral"
            app.outputToHistory("Sudan alignment worssened.", False)
          elif app.map["Sudan"].alignment == "Neutral":
            app.map["Sudan"].alignment = "Adversary"
            app.outputToHistory("Sudan alignment worssened.", False)
        app.outputToHistory(app.map["Sudan"].countryStr(), True)
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
              if app.map[country].type == "Non-Muslim":
                if app.map[country].posture == "Hard":
                  targets.append(country)
              else:
                if app.map[country].alignment == "Ally":
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
              if app.map[country].type == "Non-Muslim":
                if app.map[country].posture == "Hard":
                  targets.append(country)
              else:
                if app.map[country].alignment == "Ally":
                  targets.append(country)
          target = random.choice(targets)
          app.map[target].plots += 1
          app.outputToHistory("Place an plot in %s." % target, True)
      elif self.number == 116: # KSM
        if side == "US":
          for country in app.map:
            if app.map[country].plots > 0:
              if app.map[country].alignment == "Ally" or app.map[country].type == "Non-Muslim":
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
          if app.map["Yemen"].alignment == "Ally":
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
    self.ideology = theIdeology
    self.prestige = 0
    self.troops = 0
    self.cells = 0
    self.funding = 0
    self.startYear = 0
    self.turn = 1
    self.uCard = 1
    self.jCard = 1
    self.phase = ""
    self.map = {}
    self.mapSetup()
    self.history = []
    self.markers = []
    self.lapsing = []
    self.testUserInput = testUserInput
    if setupFuntion:
      setupFuntion(self)
    else:
      self.scenarioSetup()
      #self.testScenarioSetup()
    self.prompt = "Command: "
    self.gameOver = False
    self.backlashInPlay = False

    if self.scenario == 1:
      self.outputToHistory("Scenario: Let's Roll!", False)
    elif self.scenario == 2:
      self.outputToHistory("Scenario: You Can Call Me Al", False)
    elif self.scenario == 3:
      self.outputToHistory("Scenario: Anaconda", False)
    elif self.scenario == 4:
      self.outputToHistory("Scenario: Mission Accomplished?", False)

    if self.ideology == 1:
      self.outputToHistory("Jihadist Ideology: Normal", False)
    elif self.ideology == 2:
      self.outputToHistory("Jihadist Ideology: Attractive", False)
    elif self.ideology == 3:
      self.outputToHistory("Jihadist Ideology: Potent", False)
    elif self.ideology == 4:
      self.outputToHistory("Jihadist Ideology: Infectious", False)
    elif self.ideology == 5:
      self.outputToHistory("Jihadist Ideology: Virulent", False)

    print("")

    self.outputToHistory("Game Start")
    self.outputToHistory("")
    self.outputToHistory("[[ %d (Turn %s) ]]" % (self.startYear + (self.turn - 1), self.turn), True)
    #self.outputToHistory(self.phase)
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
    troopCount += self.troops
    if troopCount != 15:
      print("DEBUG: TROOP COUNT %d" % troopCount)
  # Countries tested test
    for country in self.map:
      badCountry = False
      if (self.map[country].sleeper_cells > 0) or (self.map[country].activeCells > 0) or (self.map[country].troops_stationed > 0) or (self.map[country].aid > 0) or  (self.map[country].regimeChange > 0) or (self.map[country].cadre > 0) or (self.map[country].plots > 0):
        if (self.map[country].governance == 0):
          badCountry = True
        if self.map[country].type == "Non-Muslim":
          if (self.map[country].posture == ""):
            badCountry = True
        elif self.map[country].type != "Iran":
          if (self.map[country].alignment == ""):
            badCountry = True
      if badCountry:
        print("DEBUG: UNTESTED COUNTRY")
        self.map[country].printCountry()

  def emptyline(self):
    print("%d (Turn %s)" % (self.startYear + (self.turn - 1), self.turn))
    #print("Enter help for a list of commands.")
    print("")

  def debugprint(self, str):
    return
    print(str)

  def outputToHistory(self, output, lineFeed = True):
    print(output)
    self.history.append(output)
    if lineFeed:
      print("")

  def mapSetup(self):
    self.map["Canada"] = Country(self, "Canada", "Non-Muslim", "", "", 1, False, 0, 0, 0, 0, False, 0)
    self.map["United States"] = Country(self, "United States", "Non-Muslim", "Hard", "", 1, False, 0, 0, 0, 0, False, 0)
    self.map["United Kingdom"] = Country(self, "United Kingdom", "Non-Muslim", "", "", 1, False, 3, 0, 0, 0, False, 0)
    self.map["Serbia"] = Country(self, "Serbia", "Non-Muslim", "", "", 1, False, 0, 0, 0, 0, False, 0)
    self.map["Israel"] = Country(self, "Israel", "Non-Muslim", "Hard", "", 1, False, 0, 0, 0, 0, False, 0)
    self.map["India"] = Country(self, "India", "Non-Muslim", "", "", 1, False, 0, 0, 0, 0, False, 0)
    self.map["Scandinavia"] = Country(self, "Scandinavia", "Non-Muslim", "", "", 1, True, 0, 0, 0, 0, False, 0)
    self.map["Eastern Europe"] = Country(self, "Eastern Europe", "Non-Muslim", "", "", 1, True, 0, 0, 0, 0, False, 0)
    self.map["Benelux"] = Country(self, "Benelux", "Non-Muslim", "", "", 1, True, 0, 0, 0, 0, False, 0)
    self.map["Germany"] = Country(self, "Germany", "Non-Muslim", "", "", 1, True, 0, 0, 0, 0, False, 0)
    self.map["France"] = Country(self, "France", "Non-Muslim", "", "", 1, True, 2, 0, 0, 0, False, 0)
    self.map["Italy"] = Country(self, "Italy", "Non-Muslim", "", "", 1, True, 0, 0, 0, 0, False, 0)
    self.map["Spain"] = Country(self, "Spain", "Non-Muslim", "", "", 1, True, 2, 0, 0, 0, False, 0)
    self.map["Russia"] = Country(self, "Russia", "Non-Muslim", "", "", 2, False, 0, 0, 0, 0, False, 0)
    self.map["Caucasus"] = Country(self, "Caucasus", "Non-Muslim", "", "", 2, False, 0, 0, 0, 0, False, 0)
    self.map["China"] = Country(self, "China", "Non-Muslim", "", "", 2, False, 0, 0, 0, 0, False, 0)
    self.map["Kenya/Tanzania"] = Country(self, "Kenya/Tanzania", "Non-Muslim", "", "", 2, False, 0, 0, 0, 0, False, 0)
    self.map["Thailand"] = Country(self, "Thailand", "Non-Muslim", "", "", 2, False, 0, 0, 0, 0, False, 0)
    self.map["Philippines"] = Country(self, "Philippines", "Non-Muslim", "", "", 2, False, 3, 0, 0, 0, False, 0)
    self.map["Morocco"] = Country(self, "Morocco", "Suni", "", "", 0, False, 0, 0, 0, 0, False, 2)
    self.map["Algeria/Tunisia"] = Country(self, "Algeria/Tunisia", "Suni", "", "", 0, False, 0, 0, 0, 0, True, 2)
    self.map["Libya"] = Country(self, "Libya", "Suni", "", "", 0, False, 0, 0, 0, 0, True, 1)
    self.map["Egypt"] = Country(self, "Egypt", "Suni", "", "", 0, False, 0, 0, 0, 0, False, 3)
    self.map["Sudan"] = Country(self, "Sudan", "Suni", "", "", 0, False, 0, 0, 0, 0, True, 1)
    self.map["Somalia"] = Country(self, "Somalia", "Suni", "", "", 0, False, 0, 0, 0, 0, False, 1)
    self.map["Jordan"] = Country(self, "Jordan", "Suni", "", "", 0, False, 0, 0, 0, 0, False, 1)
    self.map["Syria"] = Country(self, "Syria", "Suni", "", 0, 0, False, 0, 0, 0, 0, False, 2)
    self.map["Central Asia"] = Country(self, "Central Asia", "Suni", "", "", 0, False, 0, 0, 0, 0, False, 2)
    self.map["Indonesia/Malaysia"] = Country(self, "Indonesia/Malaysia", "Suni", "", "", 0, False, 0, 0, 0, 0, True, 3)
    self.map["Turkey"] = Country(self, "Turkey", "Shia-Mix", "", "", 0, False, 0, 0, 0, 0, False, 2)
    self.map["Lebanon"] = Country(self, "Lebanon", "Shia-Mix", "", "", 0, False, 0, 0, 0, 0, False, 1)
    self.map["Yemen"] = Country(self, "Yemen", "Shia-Mix", "", "", 0, False, 0, 0, 0, 0, False, 1)
    self.map["Iraq"] = Country(self, "Iraq", "Shia-Mix", "", "", 0, False, 0, 0, 0, 0, True, 3)
    self.map["Saudi Arabia"] = Country(self, "Saudi Arabia", "Shia-Mix", "", "", 0, False, 0, 2, 0, 0, True, 3)
    self.map["Gulf States"] = Country(self, "Gulf States", "Shia-Mix", "", "", 0, False, 0, 2, 0, 0, True, 3)
    self.map["Pakistan"] = Country(self, "Pakistan", "Shia-Mix", "", "", 0, False, 0, 0, 0, 0, False, 2)
    self.map["Afghanistan"] = Country(self, "Afghanistan", "Shia-Mix", "", "", 0, False, 0, 0, 0, 0, False, 1)
    self.map["Iran"] = Country(self, "Iran", "Iran", "", "Fair", 2, False, 0, 0, 0, 0, False, 0)

  #   self.map["Canada"] = Country("Canada", "Non-Muslim", "", "", 1, False, 0, 0, 0, 0, False, 0)
    self.map["Canada"].links.append(self.map["United States"])
    self.map["Canada"].links.append(self.map["United Kingdom"])
    self.map["Canada"].schengenLink = True
  #   self.map["United States"] = Country("United States", "Non-Muslim", "Hard", "", 1, False, 0, 0, 0, 0, False, 0)
    self.map["United States"].links.append(self.map["Canada"])
    self.map["United States"].links.append(self.map["United Kingdom"])
    self.map["United States"].links.append(self.map["Philippines"])
    self.map["United States"].schengenLink = True
  #   self.map["United Kingdom"] = Country("United Kingdom", "Non-Muslim", "", "", 1, False, 3, 0, 0, 0, False, 0)
    self.map["United Kingdom"].links.append(self.map["Canada"])
    self.map["United Kingdom"].links.append(self.map["United States"])
    self.map["United Kingdom"].schengenLink = True
  #   self.map["Serbia"] = Country("Serbia", "Non-Muslim", "", "", 1, False, 0, 0, 0, 0, False, 0)
    self.map["Serbia"].links.append(self.map["Russia"])
    self.map["Serbia"].links.append(self.map["Turkey"])
    self.map["Serbia"].schengenLink = True
  #   self.map["Israel"] = Country("Israel", "Non-Muslim", "Hard", "", 1, False, 0, 0, 0, 0, False, 0)
    self.map["Israel"].links.append(self.map["Lebanon"])
    self.map["Israel"].links.append(self.map["Jordan"])
    self.map["Israel"].links.append(self.map["Egypt"])
  #   self.map["India"] = Country("India", "Non-Muslim", "", "", 1, False, 0, 0, 0, 0, False, 0)
    self.map["India"].links.append(self.map["Pakistan"])
    self.map["India"].links.append(self.map["Indonesia/Malaysia"])
  #   self.map["Russia"] = Country("Russia", "Non-Muslim", "", "", 2, True, 0, 0, 0, 0, False, 0)
    self.map["Russia"].links.append(self.map["Serbia"])
    self.map["Russia"].links.append(self.map["Turkey"])
    self.map["Russia"].links.append(self.map["Caucasus"])
    self.map["Russia"].links.append(self.map["Central Asia"])
    self.map["Russia"].schengenLink = True
  #   self.map["Caucasus"] = Country("Caucasus", "Non-Muslim", "", "", 2, True, 0, 0, 0, 0, False, 0)
    self.map["Caucasus"].links.append(self.map["Russia"])
    self.map["Caucasus"].links.append(self.map["Turkey"])
    self.map["Caucasus"].links.append(self.map["Iran"])
    self.map["Caucasus"].links.append(self.map["Central Asia"])
  #   self.map["China"] = Country("China", "Non-Muslim", "", "", 2, True, 0, 0, 0, 0, False, 0)
    self.map["China"].links.append(self.map["Central Asia"])
    self.map["China"].links.append(self.map["Thailand"])
  #   self.map["Kenya/Tanzania"] = Country("Kenya/Tanzania", "Non-Muslim", "", "", 2, True, 0, 0, 0, 0, False, 0)
    self.map["Kenya/Tanzania"].links.append(self.map["Sudan"])
    self.map["Kenya/Tanzania"].links.append(self.map["Somalia"])
  #   self.map["Thailand"] = Country("Thailand", "Non-Muslim", "", "", 2, True, 0, 0, 0, 0, False, 0)
    self.map["Thailand"].links.append(self.map["China"])
    self.map["Thailand"].links.append(self.map["Philippines"])
    self.map["Thailand"].links.append(self.map["Indonesia/Malaysia"])
  #   self.map["Philippines"] = Country("Philippines", "Non-Muslim", "", "", 2, True, 3, 0, 0, 0, False, 0)
    self.map["Philippines"].links.append(self.map["United States"])
    self.map["Philippines"].links.append(self.map["Thailand"])
    self.map["Philippines"].links.append(self.map["Indonesia/Malaysia"])
  #   self.map["Morocco"] = Country("Morocco", "Suni", "", "", 0, False, 0, 0, 0, 0, False, 2)
    self.map["Morocco"].links.append(self.map["Algeria/Tunisia"])
    self.map["Morocco"].schengenLink = True
  #   self.map["Algeria/Tunisia"] = Country("Algeria/Tunisia", "Suni", "", "", 0, False, 0, 0, 0, 0, True, 2)
    self.map["Algeria/Tunisia"].links.append(self.map["Morocco"])
    self.map["Algeria/Tunisia"].links.append(self.map["Libya"])
    self.map["Algeria/Tunisia"].schengenLink = True
  #   self.map["Libya"] = Country("Libya", "Suni", "", "Adversary", 3, False, 0, 0, 0, 0, True, 1)
    self.map["Libya"].links.append(self.map["Algeria/Tunisia"])
    self.map["Libya"].links.append(self.map["Egypt"])
    self.map["Libya"].links.append(self.map["Sudan"])
    self.map["Libya"].schengenLink = True
  #   self.map["Egypt"] = Country("Egypt", "Suni", "", "", 0, False, 0, 0, 0, 0, False, 3)
    self.map["Egypt"].links.append(self.map["Libya"])
    self.map["Egypt"].links.append(self.map["Israel"])
    self.map["Egypt"].links.append(self.map["Sudan"])
  #   self.map["Sudan"] = Country("Sudan", "Suni", "", "", 0, False, 0, 0, 0, 0, True, 1)
    self.map["Sudan"].links.append(self.map["Libya"])
    self.map["Sudan"].links.append(self.map["Egypt"])
    self.map["Sudan"].links.append(self.map["Kenya/Tanzania"])
    self.map["Sudan"].links.append(self.map["Somalia"])
  #   self.map["Somalia"] = Country("Somalia", "Suni", "", "", 0, False, 0, 0, 0, 0, False, 1)
    self.map["Somalia"].links.append(self.map["Sudan"])
    self.map["Somalia"].links.append(self.map["Kenya/Tanzania"])
    self.map["Somalia"].links.append(self.map["Yemen"])
  #   self.map["Jordan"] = Country("Jordan", "Suni", "", "", 0, False, 0, 0, 0, 0, False, 1)
    self.map["Jordan"].links.append(self.map["Israel"])
    self.map["Jordan"].links.append(self.map["Syria"])
    self.map["Jordan"].links.append(self.map["Iraq"])
    self.map["Jordan"].links.append(self.map["Saudi Arabia"])
  #   self.map["Syria"] = Country("Syria", "Suni", "Adversary", "Fair", 2, False, 0, 0, 0, 0, False, 2)
    self.map["Syria"].links.append(self.map["Turkey"])
    self.map["Syria"].links.append(self.map["Lebanon"])
    self.map["Syria"].links.append(self.map["Jordan"])
    self.map["Syria"].links.append(self.map["Iraq"])
  #   self.map["Central Asia"] = Country("Central Asia", "Suni", "", "", 0, False, 0, 0, 0, 0, False, 2)
    self.map["Central Asia"].links.append(self.map["Russia"])
    self.map["Central Asia"].links.append(self.map["Caucasus"])
    self.map["Central Asia"].links.append(self.map["Iran"])
    self.map["Central Asia"].links.append(self.map["Afghanistan"])
    self.map["Central Asia"].links.append(self.map["China"])
  #   self.map["Indonesia/Malaysia"] = Country("Indonesia/Malaysia", "Suni", "", "", 0, False, 0, 0, 0, 0, True, 3)
    self.map["Indonesia/Malaysia"].links.append(self.map["Thailand"])
    self.map["Indonesia/Malaysia"].links.append(self.map["India"])
    self.map["Indonesia/Malaysia"].links.append(self.map["Philippines"])
    self.map["Indonesia/Malaysia"].links.append(self.map["Pakistan"])
  #   self.map["Turkey"] = Country("Turkey", "Shia-Mix", "", "", 0, False, 0, 0, 0, 0, False, 2)
    self.map["Turkey"].links.append(self.map["Serbia"])
    self.map["Turkey"].links.append(self.map["Russia"])
    self.map["Turkey"].links.append(self.map["Caucasus"])
    self.map["Turkey"].links.append(self.map["Iran"])
    self.map["Turkey"].links.append(self.map["Syria"])
    self.map["Turkey"].links.append(self.map["Iraq"])
    self.map["Turkey"].schengenLink = True
  #   self.map["Lebanon"] = Country("Lebanon", "Shia-Mix", "", "", 0, False, 0, 0, 0, 0, False, 1)
    self.map["Lebanon"].links.append(self.map["Syria"])
    self.map["Lebanon"].links.append(self.map["Israel"])
    self.map["Lebanon"].schengenLink = True
  #   self.map["Yemen"] = Country("Yemen", "Shia-Mix", "", "", 0, False, 0, 0, 0, 0, False, 1)
    self.map["Yemen"].links.append(self.map["Saudi Arabia"])
    self.map["Yemen"].links.append(self.map["Somalia"])
  #   self.map["Iraq"] = Country("Iraq", "Shia-Mix", "", "Adversary", 3, False, 0, 0, 0, 0, True, 3)
    self.map["Iraq"].links.append(self.map["Syria"])
    self.map["Iraq"].links.append(self.map["Turkey"])
    self.map["Iraq"].links.append(self.map["Iran"])
    self.map["Iraq"].links.append(self.map["Gulf States"])
    self.map["Iraq"].links.append(self.map["Saudi Arabia"])
    self.map["Iraq"].links.append(self.map["Jordan"])
  #   self.map["Saudi Arabia"] = Country("Saudi Arabia", "Shia-Mix", "", "Ally", 3, False, 0, 2, 0, 0, True, 3)
    self.map["Saudi Arabia"].links.append(self.map["Jordan"])
    self.map["Saudi Arabia"].links.append(self.map["Iraq"])
    self.map["Saudi Arabia"].links.append(self.map["Gulf States"])
    self.map["Saudi Arabia"].links.append(self.map["Yemen"])
  #   self.map["Gulf States"] = Country("Gulf States", "Shia-Mix", "", "Ally", 2, False, 0, 2, 0, 0, True, 3)
    self.map["Gulf States"].links.append(self.map["Iran"])
    self.map["Gulf States"].links.append(self.map["Pakistan"])
    self.map["Gulf States"].links.append(self.map["Saudi Arabia"])
    self.map["Gulf States"].links.append(self.map["Iraq"])
  #   self.map["Pakistan"] = Country("Pakistan", "Shia-Mix", "", "Neutral", 2, False, 0, 0, 0, 0, False, 2)
    self.map["Pakistan"].links.append(self.map["Iran"])
    self.map["Pakistan"].links.append(self.map["Afghanistan"])
    self.map["Pakistan"].links.append(self.map["India"])
    self.map["Pakistan"].links.append(self.map["Gulf States"])
    self.map["Pakistan"].links.append(self.map["Indonesia/Malaysia"])
  #   self.map["Afghanistan"] = Country("Afghanistan", "Shia-Mix", "", "Adversary", 4, False, 0, 0, 0, 4, False, 1)
    self.map["Afghanistan"].links.append(self.map["Central Asia"])
    self.map["Afghanistan"].links.append(self.map["Pakistan"])
    self.map["Afghanistan"].links.append(self.map["Iran"])
  #   self.map["Iran"] = Country("Iran", "Iran", "", "", 0, False, 0, 0, 0, 0, False, 0)
    self.map["Iran"].links.append(self.map["Central Asia"])
    self.map["Iran"].links.append(self.map["Afghanistan"])
    self.map["Iran"].links.append(self.map["Pakistan"])
    self.map["Iran"].links.append(self.map["Gulf States"])
    self.map["Iran"].links.append(self.map["Iraq"])
    self.map["Iran"].links.append(self.map["Turkey"])
    self.map["Iran"].links.append(self.map["Caucasus"])

  def setup_board(self, scenario):
    board_trackers = [ 'startYear' , 'turn' , 'prestige' , 'troops' , 'funding' , 'cells' , 'phase' ]
    for t in board_trackers:
      setattr(self, t, scenario[t])

    for country, state in scenario['world_state'].items():
      for k, v in state.items():
        if k in COUNTRY_STATS.keys():
          setattr(self.map[country.replace('_',' ')], k, COUNTRY_STATS[k][v])
        elif k == 'markers' :
          self.map[country.replace('_',' ')].markers.extend(v)
        else :
          setattr(self.map[country.replace('_',' ')], k, v)
    self.map["United States"].posture = scenario['posture']

  def scenarioSetup(self):
    scenarios = ''
    with open('scenarios.yml', 'r') as f:
      scenarios = yaml.load(f)

    if self.scenario == 1 :
      self.setup_board(scenarios['lets_roll']) 
    elif self.scenario == 2 :
      self.setup_board(scenarios['you_can_call_me_al']) 
      print("Remove the card Axis of Evil from the game. \n")

    elif self.scenario == 3:
      self.setup_board(scenarios['anaconda']) 
      self.markers.append("Patriot Act")

      for country in random.sample(list(self.map.keys()), 3):
        self.testCountry(country)
        self.placeCells(country, 1)

      print("Remove the cards Patriot Act and Tora Bora from the game.")
      print("")
    elif self.scenario == 4:
      self.startYear = 2003
      self.turn = 1
      self.prestige = 3
      self.troops = 0
      self.funding = 5
      self.cells = 5
      self.map["Libya"].governance = 3
      self.map["Libya"].alignment = "Adversary"
      self.map["Syria"].governance = 2
      self.map["Syria"].alignment = "Adversary"
      self.map["Syria"].sleeper_cells = 1
      self.map["Iraq"].governance = 3
      self.map["Iraq"].alignment = "Ally"
      self.map["Iraq"].troops_stationed = 6
      self.map["Iraq"].sleeper_cells = 3
      self.map["Iraq"].regimeChange = 1
      self.map["Iran"].sleeper_cells = 1
      self.map["Saudi Arabia"].governance = 3
      self.map["Saudi Arabia"].alignment = "Ally"
      self.map["Saudi Arabia"].sleeper_cells = 1
      self.map["Gulf States"].governance = 2
      self.map["Gulf States"].alignment = "Ally"
      self.map["Gulf States"].troops_stationed = 2
      self.map["Pakistan"].governance = 2
      self.map["Pakistan"].alignment = "Ally"
      self.map["Pakistan"].sleeper_cells = 1
      self.map["Pakistan"].markers.append("FATA")
      self.map["Afghanistan"].governance = 3
      self.map["Afghanistan"].alignment = "Ally"
      self.map["Afghanistan"].sleeper_cells = 1
      self.map["Afghanistan"].troops_stationed = 5
      self.map["Afghanistan"].regimeChange = 1
      self.map["Somalia"].besieged = 1
      self.map["Central Asia"].governance = 2
      self.map["Central Asia"].alignment = "Neutral"
      self.map["Indonesia/Malaysia"].governance = 2
      self.map["Indonesia/Malaysia"].alignment = "Neutral"
      self.map["Indonesia/Malaysia"].sleeper_cells = 1
      self.map["Philippines"].posture = "Soft"
      self.map["Philippines"].troops_stationed = 2
      self.map["Philippines"].sleeper_cells = 1
      self.map["United Kingdom"].posture = "Hard"
      self.markers.append("Abu Sayyaf")
      self.markers.append("Patriot Act")
      self.markers.append("NEST")
      self.markers.append("Enhanced Measures")
      self.markers.append("Renditions")
      self.markers.append("Wiretapping")
      possibles = []
      for country in self.map:
        if self.map[country].schengen:
          self.testCountry(country)
      print("")
      print("Remove the cards Patriot Act, Tora Bora, NEST, Abu Sayyaf, KSM and Iraqi WMD from the game.")
      print("")
    goodRes = 0
    islamRes = 0
    goodC = 0
    islamC = 0
    worldPos = 0
    for country in self.map:
      if self.map[country].type == "Shia-Mix" or self.map[country].type == "Suni":
        if self.map[country].governance == 1:
          goodC += 1
          goodRes += self.countryResources(country)
        elif self.map[country].governance == 2:
          goodC += 1
        elif self.map[country].governance == 3:
          islamC += 1
        elif self.map[country].governance == 4:
          islamC += 1
          islamRes += self.countryResources(country)
      elif self.map[country].type != "Iran" and self.map[country].name != "United States":
        if self.map[country].posture == "Hard":
          worldPos += 1
        elif self.map[country].posture == "Soft":
          worldPos -= 1
    print("Good Resources   : %d" % goodRes)
    print("Islamic Resources: %d" % islamRes)
    print("---")
    print("Good/Fair Countries   : %d" % goodC)
    print("Poor/Islamic Countries: %d" % islamC)
    print("")
    print("GWOT")
    print("US Posture: %s" % self.map["United States"].posture)
    if worldPos > 0:
      worldPosStr = "Hard"
    elif worldPos < 0:
      worldPosStr = "Soft"
    else:
      worldPosStr = "Even"
    print("World Posture: %s %d" % (worldPosStr, abs(worldPos)))
    print("US Prestige: %d" % self.prestige)
    print("")


  def testScenarioSetup(self):
    if self.scenario == 1 or self.scenario == 2: # Let's Roll
      self.startYear = 2001
      self.turn = 1
      self.prestige = 7
      self.troops = 11
      self.funding = 9
      self.cells = 11
      self.phase = "Jihadist Action Phase"
      self.map["France"].posture = "Hard"
      self.map["France"].cadre = 1
      self.map["Spain"].posture = "Soft"
      self.map["Spain"].sleeper_cells = 1
      self.map["Germany"].posture = "Hard"
      self.map["Germany"].activeCells = 1
      self.map["Germany"].sleeper_cells = 1
      self.map["United States"].plots = 1
      self.map["Libya"].governance = 3
      self.map["Libya"].alignment = "Adversary"
      self.map["Syria"].governance = 2
      self.map["Syria"].alignment = "Adversary"
      self.map["Iraq"].governance = 3
      self.map["Iraq"].alignment = "Adversary"
      self.map["Iraq"].plots = 2
      self.map["Saudi Arabia"].governance = 3
      self.map["Saudi Arabia"].alignment = "Ally"
      self.map["Saudi Arabia"].troops_stationed = 2
      self.map["Pakistan"].governance = 3
      self.map["Pakistan"].alignment = "Ally"
      self.map["Pakistan"].troops_stationed = 2
      self.map["Pakistan"].activeCells = 4
      self.map["Gulf States"].governance = 3
      self.map["Gulf States"].alignment = "Ally"
      self.map["Gulf States"].troops_stationed = 2
      self.map["Gulf States"].sleeper_cells = 10
      self.map["Gulf States"].activeCells = 4
      self.map["Pakistan"].governance = 2
      self.map["Pakistan"].alignment = "Neutral"
      self.map["Afghanistan"].governance = 4
      self.map["Afghanistan"].alignment = "Adversary"
      self.map["Afghanistan"].sleeper_cells = 4
      self.map["Somalia"].besieged = 1
      if self.scenario == 1:
        self.map["United States"].posture = "Hard"
      else:
        self.map["United States"].posture = "Soft"

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
    #print("DEBUG: base roll:%d" % modRoll)

    if self.prestige <= 3:
      modRoll -= 1
      self.outputToHistory("-1 for Prestige", False)
    elif self.prestige >= 7 and self.prestige <=9:
      modRoll += 1
      self.outputToHistory("+1 for Prestige", False)
    elif self.prestige >= 10:
      modRoll += 2
      self.outputToHistory("+2 for Prestige", False)
    #print("DEBUG: w/prestige mod:%d" % modRoll)

    if self.map[country].alignment == "Ally" and self.map[country].governance == 2:
      modRoll -= 1
      self.outputToHistory("-1 for Attempt to shift to Good", False)
    #print("DEBUG: w/to good mod:%d" % modRoll)

    if useGWOTPenalty:
      modRoll += self.gwotPenalty()
      if self.gwotPenalty() != 0:
        self.outputToHistory("-1 for GWOT Relations Penalty", False)
    #print("DEBUG: w/GWOT penalty:%d" % modRoll)

    if self.map[country].aid > 0:
      modRoll += 1
      self.outputToHistory("+1 for Aid", False)
    #print("DEBUG: w/aid:%d" % modRoll)

    for adj in self.map[country].links:
      if adj.alignment == "Ally" and adj.governance == 1:
        modRoll += 1
        self.outputToHistory("+1 for Adjacent Good Ally", False)
        break
    #print("DEBUG: w/adj good:%d" % modRoll)
    return modRoll

  def gwotPenalty(self):
    worldPos = 0
    for country in self.map:
      if self.map[country].type == "Non-Muslim" and self.map[country].name != "United States":
        if self.map[country].posture == "Hard":
          worldPos += 1
        elif self.map[country].posture == "Soft":
          worldPos -= 1
    if worldPos > 0:
      worldPosStr = "Hard"
    elif worldPos < 0:
      worldPosStr = "Soft"
    else:
      worldPosStr = "Even"
    if worldPos > 3:
      worldPos = 3
    elif worldPos < -3:
      worldPos = -3
    if self.map["United States"].posture != worldPosStr:
      return -(abs(worldPos))
    else:
      return 0

  def changePrestige(self, delta, lineFeed = True):
    self.prestige += delta
    if self.prestige < 1:
      self.prestige = 1
    elif self.prestige > 12:
      self.prestige = 12
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
      self.map[country].cadre = 0
      self.cells -= cellsToMove
      self.outputToHistory("%d Sleeper Cell(s) placed in %s" % (cellsToMove, country), False)
      self.outputToHistory(self.map[country].countryStr(), True)

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
      self.map[country].activeCells -= 1
      self.cells += 1
      self.outputToHistory("Active Cell removed from %s." % country, True)
    if self.map[country].totalCells() == 0:
      self.outputToHistory("Cadre added in %s." % country, True)
      self.map[country].cadre = 1

  def removeAllCellsFromCountry(self, country):
    cellsToRemove = self.map[country].totalCells()
    if self.map[country].sleeper_cells > 0:
      numCells = self.map[country].sleeper_cells
      self.map[country].sleeper_cells -= numCells
      self.cells += numCells
      self.outputToHistory("%d Sleeper Cell(s) removed from %s." % (numCells, country), False)
    if self.map[country].activeCells > 0:
      numCells = self.map[country].activeCells
      self.map[country].activeCells -= numCells
      self.cells += numCells
      self.outputToHistory("%d Active Cell(s) removed from %s." % (numCells, country), False)
    if cellsToRemove > 0:
      self.outputToHistory("Cadre added in %s." % country, False)
      self.map[country].cadre = 1

  def improveGovernance(self, country):
    self.map[country].governance -= 1
    if self.map[country].governance <= 1:
      self.map[country].governance = 1
      self.map[country].regimeChange = 0
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
      if self.map[country].governance == 4:
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
      if self.map[country].regimeChange > 0:
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
      if self.map[country].totalCells(False) > 0 or self.map[country].cadre > 0:
        if self.map[country].troops() > 0 or self.map[country].type == "Non-Muslim" or self.map[country].alignment == "Ally":
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
      self.outputToHistory(self.map[country].countryStr(), True)
    else:
      if self.map[country].alignment == "Neutral":
        self.map[country].alignment = "Ally"
        self.outputToHistory("* WoI in %s succeeded - Alignment now Ally." % country, False)
        self.outputToHistory(self.map[country].countryStr(), True)
      elif self.map[country].alignment == "Ally":
        self.improveGovernance(country)
        self.outputToHistory("* WoI in %s succeeded - Governance now %s." % (country, self.map[country].govStr()), False)
        self.outputToHistory(self.map[country].countryStr(), True)

  def handleAlert(self, country):
    if self.map[country].plots > 0:
      self.map[country].plots -= 1
      self.outputToHistory("* Alert in %s - %d plot(s) remain." % (country, self.map[country].plots))

  def handleReassessment(self):
    if self.map["United States"].posture == "Hard":
      self.map["United States"].posture = "Soft"
    else:
      self.map["United States"].posture = "Hard"
    self.outputToHistory("* Reassessment = US Posture now %s" % self.map["United States"].posture)

  def handleRegimeChange(self, where, moveFrom, howMany, govRoll, prestigeRolls):
    if self.map["United States"].posture == "Soft":
      return
    if moveFrom == 'track':
      self.troops -= howMany
    else:
      self.map[moveFrom].changeTroops(-howMany)
    self.map[where].changeTroops(howMany)
    sleepers = self.map[where].sleeper_cells
    self.map[where].sleeper_cells = 0
    self.map[where].activeCells += sleepers
    self.map[where].alignment = "Ally"
    if govRoll <= 4:
      self.map[where].governance = 3
    else:
      self.map[where].governance = 2
    self.map[where].regimeChange = 1
    presMultiplier = 1
    if prestigeRolls[0] <= 4:
      presMultiplier = -1
    self.changePrestige(min(prestigeRolls[1], prestigeRolls[2]) * presMultiplier)
    self.outputToHistory("* Regime Change in %s" % where, False)
    self.outputToHistory(self.map[where].countryStr(), False)
    if moveFrom == "track":
      self.outputToHistory("%d Troops on Troop Track" % self.troops, False)
    else:
      self.outputToHistory("%d Troops in %s" % (self.map[moveFrom].troops(), moveFrom), False)
    self.outputToHistory("US Prestige %d" % self.prestige)
    if where == "Iraq" and "Iraqi WMD" in self.markers:
      self.markers.remove("Iraqi WMD")
      self.outputToHistory("Iraqi WMD no longer in play.", True)
    if where == "Libya" and "Libyan WMD" in self.markers:
      self.markers.remove("Libyan WMD")
      self.outputToHistory("Libyan WMD no longer in play.", True)

  def handleWithdraw(self, moveFrom, moveTo, howMany, prestigeRolls):
    if self.map["United States"].posture == "Hard":
      return
    self.map[moveFrom].changeTroops(-howMany)
    if moveTo == "track":
      self.troops += howMany
    else:
      self.map[moveTo].changeTroops(howMany)
    self.map[moveFrom].aid = 0
    self.map[moveFrom].besieged = 1
    presMultiplier = 1
    if prestigeRolls[0] <= 4:
      presMultiplier = -1
    self.changePrestige(min(prestigeRolls[1], prestigeRolls[2]) * presMultiplier)
    self.outputToHistory("* Withdraw troops from %s" % moveFrom, False)
    self.outputToHistory(self.map[moveFrom].countryStr(), False)
    if moveTo == "track":
      self.outputToHistory("%d Troops on Troop Track" % self.troops, False)
    else:
      self.outputToHistory("%d Troops in %s" % (self.map[moveTo].troops(), moveTo), False)
      self.outputToHistory(self.map[moveTo].countryStr(), False)
    self.outputToHistory("US Prestige %d" % self.prestige)

  def handleDisrupt(self, where):
    numToDisrupt = 1
    if "Al-Anbar" in self.markers and (where == "Iraq" or where == "Syria"):
      numToDisrupt = 1
    elif self.map[where].troops() >= 2 or self.map[where].posture == "Hard":
      numToDisrupt = min(2, self.map[where].totalCells(False))
    if self.map[where].totalCells(False) <= 0 and self.map[where].cadre > 0:
      if "Al-Anbar" not in self.markers:
        self.outputToHistory("* Cadre removed in %s" % where)
        self.map[where].cadre = 0
    elif self.map[where].totalCells(False) <= numToDisrupt:
      self.outputToHistory("* %d cell(s) disrupted in %s." % (self.map[where].totalCells(False), where), False)
      if self.map[where].sleeper_cells > 0:
        self.map[where].activeCells += self.map[where].sleeper_cells
        numToDisrupt -= self.map[where].sleeper_cells
        self.map[where].sleeper_cells = 0
      if numToDisrupt > 0:
        self.map[where].activeCells -= numToDisrupt
        self.cells += numToDisrupt
        if self.map[where].activeCells < 0:
          self.map[where].activeCells = 0
        if self.cells > 15:
          self.cells = 15
      if self.map[where].totalCells(False) <= 0:
        self.outputToHistory("Cadre added in %s." % where, False)
        self.map[where].cadre = 1
      if self.map[where].troops() >= 2:
        self.prestige += 1
        if self.prestige > 12:
          self.prestige = 12
        self.outputToHistory("US Prestige now %d." % self.prestige, False)
      self.outputToHistory(self.map[where].countryStr(), True)
    else:
      if self.map[where].activeCells == 0:
        self.map[where].activeCells += numToDisrupt
        self.map[where].sleeper_cells -= numToDisrupt
        self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where), False)
      elif self.map[where].sleeper_cells == 0:
        self.map[where].activeCells -= numToDisrupt
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
            self.map[where].activeCells -= numToDisrupt
            self.cells += numToDisrupt
            self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where))
          else:
            self.map[where].sleeper_cells -= numToDisrupt
            self.map[where].activeCells += numToDisrupt
            self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where))
        else:
          disStr = None
          while not disStr:
            if self.map[where].sleeper_cells >= 2 and self.map[where].activeCells >= 2:
              input = self.my_raw_input("You can disrupt two cells. Enter aa, as, or ss for active or sleeper cells: ")
              input = input.lower()
              if input == "aa" or input == "as" or input == "sa" or input == "ss":
                disStr = input
            elif self.map[where].sleeper_cells >= 2:
              input = self.my_raw_input("You can disrupt two cells. Enter as, or ss for active or sleeper cells: ")
              input = input.lower()
              if input == "as" or input == "sa" or input == "ss":
                disStr = input
            elif self.map[where].activeCells >= 2:
              input = self.my_raw_input("You can disrupt two cells. Enter aa, or as for active or sleeper cells: ")
              input = input.lower()
              if input == "as" or input == "sa" or input == "aa":
                disStr = input
          if input == "aa":
            self.map[where].activeCells -= 2
            self.cells += 2
            self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where))
          elif input == "as" or input == "sa":
            self.map[where].sleeper_cells -= 1
            self.cells += 1
            self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where))
          else:
            self.map[where].sleeper_cells -= 2
            self.map[where].activeCells += 2
            self.outputToHistory("* %d cell(s) disrupted in %s." % (numToDisrupt, where))
      if self.map[where].troops() >= 2:
        self.prestige += 1
        if self.prestige > 12:
          self.prestige = 12
        self.outputToHistory("US Prestige now %d." % self.prestige, False)
      self.outputToHistory(self.map[where].countryStr(), True)

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
      self.map[country].activeCells += sleepers
      self.outputToHistory("All cells go Active", False)
      if ((failures >= 2  and self.map[country].besieged == 0) or (failures == 3 and self.map[country].besieged == 1))  and (len(rollList) == 3) and self.map[country].governance == 3:
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
        self.map[country].activeCells += 1
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
      self.map[country].regimeChange = 0
      if self.map[country].besieged > 0:
        self.outputToHistory("Besieged Regime marker removed.", False)

      self.map[country].besieged = 0
      self.map[country].aid = 0
      self.funding = min(9, self.funding + self.countryResources(country))
      self.outputToHistory("Funding now %d" % self.funding, False)
      if self.map[country].troops() > 0:
        self.prestige = 1
        self.outputToHistory("Troops present so US Prestige now 1", False)
    if self.ideology <= 4:
      for i in range(failures):
        if self.map[country].numActiveCells() > 0:
          self.map[country].removeActiveCell()
        else:
          self.map[country].sleeper_cells -= 1
          self.outputToHistory("Sleeper cell Removed to Funding Track", False)
          self.cells += 1
    self.outputToHistory(self.map[country].countryStr(), False)
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
      if self.map[country].type == "Suni" or self.map[country].type == "Shia-Mix":
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
        if self.map[country].alignment == "Ally" and self.map[country].governance != 4:
          possible.append(country)
      elif isAlJazeera:
        if country == "Saudi Arabia" or self.isAdjacent(country, "Saudi Arabia"):
          if self.map[country].troops() > 0:
            possible.append(country)
      elif (self.map[country].type == "Shia-Mix" or self.map[country].type == "Suni") and (self.map[country].governance == 1 or self.map[country].governance == 2) and (self.map[country].totalCells(True) > 0):
        if "Benazir Bhutto" in self.markers and country == "Pakistan":
          continue
        possible.append(country)
    if len(possible) == 0:
      return False
    else:
      countryScores = {}
      for country in possible:
        if self.map[country].governance == 1:
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


      if (self.map[country].totalCells(True) > 0 or (self.map[country].cadre > 0)) or (isMadrassas and self.map[country].governance > 2):
        #countryScores[country] = 0
        if (self.map[country].regimeChange > 0) and (self.map[country].troops() - self.map[country].totalCells(True)) >= 5:
          self.debugprint(("a"))
          countryScores[country] = 100000000
        elif ((self.map[country].governance == 4) and (self.map[country].totalCells(True) < (2 * ops))):
          davex = self.map[country].totalCells(True)
          self.debugprint(("here: recruit with remaining %d ops" % davex))
          countryScores[country] = 10000000
        elif (self.map[country].governance != 4) and (self.map[country].regimeChange <= 0):
          self.debugprint(("b"))
          if self.map[country].recruit > 0:
            countryScores[country] = (self.map[country].recruit * 1000000)
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
    if (self.map[country].regimeChange or self.map[country].governance == 4):
      if self.map[country].regimeChange:
        self.outputToHistory("Recruit to Regime Change country automatically successful.", False)
      else:
        self.outputToHistory("Recruit to Islamic Rule country automatically successful.", False)
      self.cells -= cellsToRecruit
      self.map[country].sleeper_cells += cellsToRecruit

      if cellsToRecruit == 0 and isJihadistVideos:
        self.map[country].cadre = 1
        self.outputToHistory("No cells available to recruit.  Cadre added.", False)
        self.outputToHistory(self.map[country].countryStr(), True)
        return ops - 1;
      else:
        self.map[country].cadre = 0

      self.outputToHistory("%d sleeper cells recruited to %s." % (cellsToRecruit, country), False)
      self.outputToHistory(self.map[country].countryStr(), True)
      if self.ideology >= 2:
        return ops - ((cellsToRecruit / 2) + (cellsToRecruit % 2))
      else:
        return (ops - cellsToRecruit)
    else:
      opsRemaining = ops
      i = 0

      if self.numCellsAvailable(isJihadistVideos) <= 0 and opsRemaining > 0:
        self.map[country].cadre = 1
        self.outputToHistory("No cells available to recruit.  Cadre added.", False)
        self.outputToHistory(self.map[country].countryStr(), True)
        return ops - 1;
      else:
        while self.numCellsAvailable(isMadrassas or isJihadistVideos) > 0 and opsRemaining > 0:
          if recruitOverride:
            recVal = recruitOverride
          elif self.map[country].recruit > 0:
            recVal = self.map[country].recruit
          else:
            recVal = self.map[country].governance
          if rolls[i] <= recVal:
            if self.ideology >= 2:
              cellsMoving = min(self.numCellsAvailable(isMadrassas or isJihadistVideos), 2)
            else:
              cellsMoving = min(self.numCellsAvailable(isMadrassas or isJihadistVideos), 1)
            self.cells -= cellsMoving
            self.map[country].sleeper_cells += cellsMoving
            self.map[country].cadre = 0
            self.outputToHistory("Roll successful, %d sleeper cell(s) recruited." % cellsMoving, False)
          else:
            self.outputToHistory("Roll failed.", False)
            if isJihadistVideos:
              self.map[country].cadre = 1
              self.outputToHistory("Cadre added.", False)
          opsRemaining -= 1
          i += 1
        self.outputToHistory(self.map[country].countryStr(), True)
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
        if (self.map[country].governance != 4) and ((self.map[country].besieged > 0) or (self.map[country].regimeChange > 0) or (self.map[country].aid > 0)):
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
      if (self.map[country].governance == 3) and (((self.map[country].totalCells(True) + 2) - self.map[country].troops()) >= self.extraCellsNeededForMajorJihad()):
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
      if ((self.map[country].governance == 1) or (self.map[country].governance == 2)) and ((self.map[country].type == "Suni") or (self.map[country].type == "Shia-Mix")):
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
    if self.map["United States"].posture == "Hard":
      for country in self.map:
        if self.map[country].type == "Non-Muslim" and self.map[country].posture == "":
          if (not isRadicalization) and ("Biometrics" in self.lapsing) and (not self.adjacentCountryHasCell(country)):
            continue
          subdests.append(country)
    else:
      for country in self.map:
        if country != "United States" and self.map[country].type == "Non-Muslim" and self.map[country].posture == "Soft":
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
    if self.map["United States"].posture == "Hard":
      for country in self.map:
        if self.map[country].schengen and self.map[country].posture == "":
          subdests.append(country)
          print("SCHENGEN:", country)
    else:
      for country in self.map:
        if country != "United States" and self.map[country].schengen and self.map[country].posture == "Soft":
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
      if self.map[country].activeCells > 0:
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
      if self.map[country].governance == 4:
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
      if self.map[country].regimeChange > 0:
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
    if self.map[country].type == "Non-Muslim" and self.map[country].posture == "":
      testRoll = random.randint(1,6)
      if testRoll <= 4:
        self.map[country].posture = "Soft"
      else:
        self.map[country].posture = "Hard"
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
        if self.map[country].governance == 1:
          dict["Good"].append(country)
        elif self.map[country].governance == 2:
          dict["Fair"].append(country)
        elif self.map[country].governance == 3:
          dict["Poor"].append(country)
    return dict

  def getCountriesWithTroopsByGovernance(self):
    dict = {}
    dict["Good"] = []
    dict["Fair"] = []
    dict["Poor"] = []
    for country in self.map:
      if self.map[country].troops() > 0:
        if self.map[country].governance == 1:
          dict["Good"].append(country)
        elif self.map[country].governance == 2:
          dict["Fair"].append(country)
        elif self.map[country].governance == 3:
          dict["Poor"].append(country)
    return dict

  def getCountriesWithAidByGovernance(self):
    dict = {}
    dict["Good"] = []
    dict["Fair"] = []
    dict["Poor"] = []
    for country in self.map:
      if self.map[country].aid > 0:
        if self.map[country].governance == 1:
          dict["Good"].append(country)
        elif self.map[country].governance == 2:
          dict["Fair"].append(country)
        elif self.map[country].governance == 3:
          dict["Poor"].append(country)
    return dict

  def getNonMuslimCountriesByGovernance(self):
    dict = {}
    dict["Good"] = []
    dict["Fair"] = []
    dict["Poor"] = []
    for country in self.map:
      if (country != "United States") and (self.map[country].type == "Non-Muslim"):
        if self.map[country].governance == 1:
          dict["Good"].append(country)
        elif self.map[country].governance == 2:
          dict["Fair"].append(country)
        elif self.map[country].governance == 3:
          dict["Poor"].append(country)
    return dict

  def getMuslimCountriesByGovernance(self):
    dict = {}
    dict["Good"] = []
    dict["Fair"] = []
    dict["Poor"] = []
    for country in self.map:
      if self.map[country].type != "Non-Muslim":
        if self.map[country].governance == 1:
          dict["Good"].append(country)
        elif self.map[country].governance == 2:
          dict["Fair"].append(country)
        elif self.map[country].governance == 3:
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
        if self.map[sources[i]].activeCells > 0:
          self.map[sources[i]].activeCells -= 1
        else:
          self.map[sources[i]].sleeper_cells -= 1
        self.map[destinations[i]].sleeper_cells += 1
        self.outputToHistory(self.map[sources[i]].countryStr(), False)
        self.outputToHistory(self.map[destinations[i]].countryStr(), True)
      else:
        if self.map[sources[i]].activeCells > 0:
          self.map[sources[i]].activeCells -= 1
        else:
          self.map[sources[i]].sleeper_cells -= 1
        self.cells += 1
        self.outputToHistory(self.map[sources[i]].countryStr(), True)
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
          self.map[country].activeCells += 1
        self.map[country].plots += successes
        self.outputToHistory("%d Plot(s) placed in %s." % (successes, country), False)
        if "Abu Sayyaf" in self.markers and country == "Philippines" and self.map[country].troops() <= self.map[country].totalCells() and successes > 0:
          self.outputToHistory("Prestige loss due to Abu Sayyaf.", False)
          self.changePrestige(-successes)
        if "NEST" in self.markers and country == "Unites States":
          self.outputToHistory("NEST in play. If jihadists have WMD, all plots in the US placed face up.", False)
        self.outputToHistory(self.map[country].countryStr(), True)
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
    if self.prestige >= 4:
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
    if self.gwotPenalty() >= 0:
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
        self.outputToHistory(self.map[country].countryStr(), True)
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
#           if self.map[location].activeCells == 0:
#             self.map[location].activeCells += 1
#             self.map[location].sleeper_cells -= 1
          opsRemaining -= 1
  # Fourth box
    while opsRemaining > 0:
      possibles = []
      for country in self.map:
        if (self.map[country].type == "Shia-Mix" or self.map[country].type == "Suni") and (self.map[country].governance == 1 or self.map[country].governance == 2):
          possibles.append(country)
      if len(possibles) == 0:
        self.outputToHistory("--> No remaining Good or Fair countries.", True)
        break
      else:
        location = random.choice(possibles)
        self.map[location].governance += 1
        self.outputToHistory("--> Governance in %s worsens to %s." % (location, self.map[location].govStr()), True)
        self.outputToHistory(self.map[location].countryStr(), True)
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
          self.map["United States"].posture = "Soft"
        else:
          self.map["United States"].posture = "Hard"
        self.outputToHistory("US Posture now %s" % self.map["United States"].posture, True)
    elif self.map[country].type != "Non-Muslim":
      if not isBacklash:
        if self.map[country].governance == 1:
          self.changeFunding(2)
        else:
          self.changeFunding(1)
        self.outputToHistory("Jihadist Funding now %d" % self.funding, False)
      else:
        if plotType == "WMD":
          self.funding = 1
        else:
          self.funding -= 1
          if self.map[country].governance == 1:
            self.funding -= 1
          if self.funding < 1:
            self.funding = 1
        self.outputToHistory("BACKLASH: Jihadist Funding now %d" % self.funding, False)
      if self.map[country].troops() > 0:
        if plotType == "WMD":
          self.prestige = 1
        else:
          self.prestige -= 1
        if self.prestige < 1:
          self.prestige = 1
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
        if self.map[country].governance == 3 and successes > 0:
          self.outputToHistory("Governance stays at %s" % self.map[country].govStr(), True)
        while successes > 0 and self.map[country].governance < 3:
          self.map[country].governance += 1
          successes -= 1
          self.outputToHistory("Governance to %s" % self.map[country].govStr(), True)
    elif self.map[country].type == "Non-Muslim":
      if country == "Israel" and "Abbas" in self.markers:
        self.markers.remove("Abbas")
        self.outputToHistory("Abbas no longer in play.", True)
      if country == "India" and "Indo-Pakistani Talks" in self.markers:
        self.markers.remove("Indo-Pakistani Talks")
        self.outputToHistory("Indo-Pakistani Talks no longer in play.", True)
      if plotType == "WMD":
        self.funding = 9
      else:
        if self.map[country].governance == 1:
          self.changeFunding(plotType * 2)
        else:
          self.changeFunding(plotType)
      self.outputToHistory("Jihadist Funding now %d" % self.funding, False)
      if country != "Israel":
        if postureRoll <= 4:
          self.map[country].posture = "Soft"
        else:
          self.map[country].posture = "Hard"
        self.outputToHistory("%s Posture now %s" % (country, self.map[country].posture), True)

      if self.map[country].troops() > 0:
        if plotType == "WMD":
          self.prestige = 1
        else:
          self.prestige -= 1
        if self.prestige < 1:
          self.prestige = 1
        self.outputToHistory("Troops present so US Prestige now %d" % self.prestige, False)


      if self.map[country].schengen:
        for i in range(len(schCountries)):
          if schPostureRolls[i] <= 4:
            self.map[schCountries[i]].posture = "Soft"
          else:
            self.map[schCountries[i]].posture = "Hard"
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
      self.map[country].posture = "Hard"
      self.outputToHistory("* War of Ideas in %s - Posture Hard" % country, False)
      if self.map["United States"].posture == "Hard":
        self.changePrestige(1)
    else:
      self.map[country].posture = "Soft"
      self.outputToHistory("* War of Ideas in %s - Posture Soft" % country, False)
      if self.map["United States"].posture == "Soft":
        self.changePrestige(1)

  def executeCardEuroIslam(self, posStr):
    self.map["Benelux"].posture = posStr
    if self.numIslamicRule() == 0:
      self.funding -= 1
      if self.funding < 1:
        self.funding = 1
      self.outputToHistory("Jihadist Funding now %d" % self.funding, False)
    self.outputToHistory(self.map["Benelux"].countryStr(), True)

  def executeCardLetsRoll(self, plotCountry, postureCountry, postureStr):
    self.map[plotCountry].plots = max(0, self.map[plotCountry].plots - 1)
    self.outputToHistory("Plot removed from %s." % plotCountry, False)
    self.map[postureCountry].posture = postureStr
    self.outputToHistory("%s Posture now %s." % (postureCountry, postureStr), False)
    self.outputToHistory(self.map[plotCountry].countryStr(), False)
    self.outputToHistory(self.map[postureCountry].countryStr(), True)

  def executeCardHEU(self, country, roll):
    if roll <= self.map[country].governance:
      self.outputToHistory("Add a WMD to available Plots.", True)
    else:
      self.removeCell(country)

  def executeCardUSElection(self, postureRoll):
    if postureRoll <= 4:
      self.map["United States"].posture = "Soft"
      self.outputToHistory("United States Posture now Soft.", False)
    else:
      self.map["United States"].posture = "Hard"
      self.outputToHistory("United States Posture now Hard.", False)
    if self.gwotPenalty() == 0:
      self.changePrestige(1)
    else:
      self.changePrestige(-1)

  def listCountriesInParam(self, needed = None):
    print("")
    print("Contries")
    print("--------")
    for country in needed:
      self.map[country].printCountry()
    print("")

  def listCountriesWithTroops(self, needed = None):
    print("")
    print("Contries with Troops")
    print("--------------------")
    if needed == None:
      needed = 0
    if self.troops > needed:
      print("Troop Track: %d" % self.troops)
    for country in self.map:
      if self.map[country].troops() > needed:
        print("%s: %d" % (country, self.map[country].troops()))
    print("")

  def listDeployOptions(self, na = None):
    print("")
    print("Deploy Options")
    print("--------------")
    for country in self.map:
      if self.map[country].alignment == "Ally" or ("Abu Sayyaf" in self.markers and country == "Philippines"):
        print("%s: %d troops" % (country, self.map[country].troops()))
    print("")

  def listDisruptableCountries(self, na = None):
    print("")
    print("Disruptable Countries")
    print("--------------------")
    for country in self.map:
      if self.map[country].sleeper_cells + self.map[country].activeCells > 0 or self.map[country].cadre > 0:
        if self.map[country].troops() > 0 or self.map[country].type == "Non-Muslim" or self.map[country].alignment == "Ally":
          postureStr = ""
          troopsStr = ""
          if self.map[country].type == "Non-Muslim":
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
      if self.map[country].alignment == "Neutral" or self.map[country].alignment == "Ally" or self.map[country].governance == 0:
        print("%s, %s %s - %d Active Cells, %d Sleeper Cells, %d Cadre, %d troops" % (country, self.map[country].govStr(), self.map[country].alignment, self.map[country].activeCells, self.map[country].sleeper_cells, self.map[country].cadre, self.map[country].troops()))
    for country in self.map:
      if self.map[country].type == "Non-Muslim" and country != "United States" and self.map[country].posture == "Hard":
        print("%s, Posture %s" % (country, self.map[country].posture))
    for country in self.map:
      if self.map[country].type == "Non-Muslim" and country != "United States" and self.map[country].posture == "Soft":
        print("%s, Posture %s" % (country, self.map[country].posture))
    for country in self.map:
      if self.map[country].type == "Non-Muslim" and country != "United States" and self.map[country].posture == "":
        print("%s, Untested" % country)

  def listPlotCountries(self, na = None):
    print("")
    print("Contries with Active Plots")
    print("--------------------------")
    for country in self.map:
      if self.map[country].plots > 0:
        self.map[country].printCountry()
    print("")

  def listIslamicCountries(self, na = None):
    print("")
    print("Islamic Rule Countries")
    print("----------------------")
    for country in self.map:
      if self.map[country].governance == 4:
        self.map[country].printCountry()
    print("")

  def listRegimeChangeCountries(self, na = None):
    print("")
    print("Regime Change Countries")
    print("-----------------------")
    for country in self.map:
      if self.map[country].regimeChange > 0:
        self.map[country].printCountry()
    print("")

  def listRegimeChangeWithTwoCells(self, na = None):
    print("")
    print("Regime Change Countries with Two Cells")
    print("---------------------------------------")
    for country in self.map:
      if self.map[country].regimeChange > 0:
        if self.map[country].totalCells() >= 2:
          self.map[country].printCountry()
    print("")

  def listCountriesWithCellAndAdjacentTroops(self, na = None):
    print("")
    print("Countries with Cells and with Troops or adjacent to Troops")
    print("----------------------------------------------------------")
    for country in self.map:
      if self.map[country].totalCells(True) > 0:
        if self.map[country].troops() > 0:
          self.map[country].printCountry()
        else:
          for subCountry in self.map:
            if subCountry != country:
              if self.map[subCountry].troops() > 0 and self.isAdjacent(country, subCountry):
                self.map[country].printCountry()
                break
    print("")

  def listAdversaryCountries(self, na = None):
    print("")
    print("Adversary Countries")
    print("-------------------")
    for country in self.map:
      if self.map[country].alignment == "Adversary":
        self.map[country].printCountry()
    print("")

  def listGoodAllyPlotCountries(self, na = None):
    print("")
    print("Ally or Good Countries with Plots")
    print("---------------------------------")
    for country in self.map:
      if self.map[country].plots > 0:
        if self.map[country].alignment == "Ally" or self.map[country].governance == 1:
          self.map[country].printCountry()
    print("")

  def listMuslimCountriesWithCells(self, na = None):
    print("")
    print("Muslim Countries with Cells")
    print("---------------------------")
    for country in self.map:
      if self.map[country].totalCells(True) > 0:
        if self.map[country].type == "Shia-Mix" or self.map[country].type == "Suni":
          self.map[country].printCountry()
    print("")

  def listBesiegedCountries(self, na = None):
    print("")
    print("Besieged Regimes")
    print("----------------")
    for country in self.map:
      if self.map[country].besieged > 0:
        self.map[country].printCountry()
    print("")

  def listShiaMixRegimeChangeCountriesWithCells(self, na = None):
    print("")
    print("Shia-Mix Regime Change Countries with Cells")
    print("-------------------------------------------")
    for country in self.map:
      if self.map[country].type == "Shia-Mix":
        if self.map[country].regimeChange > 0:
          if (self.map[country].totalCells(True)) > 0:
            self.map[country].printCountry()
    print("")

  def listShiaMixCountries(self, na = None):
    print("")
    print("Shia-Mix Countries")
    print("------------------")
    for country in self.map:
      if self.map[country].type == "Shia-Mix":
        self.map[country].printCountry()
    print("")

  def listShiaMixCountriesWithCellsTroops(self, na = None):
    print("")
    print("Shia-Mix Countries with Cells and Troops")
    print("----------------------------------------")
    for country in self.map:
      if self.map[country].type == "Shia-Mix":
        if self.map[country].troops() > 0 and self.map[country].totalCells() > 0:
          self.map[country].printCountry()
    print("")

  def listSchengenCountries(self, na = None):
    print("")
    print("Schengen Countries")
    print("------------------")
    for country in self.map:
      if self.map[country].schengen > 0:
        self.map[country].printCountry()
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
        if self.map[country].type == "Non-Muslim":
          if self.map[country].posture == "Hard":
            self.map[country].printCountry()
        else:
          if self.map[country].alignment == "Ally":
            self.map[country].printCountry()

  def do_status(self, rest):

    if rest:
      goodCountry = False
      possible = []
      for country in self.map:
        if rest.lower() == country.lower():
          possible = []
          possible.append(country)
          break
        elif rest.lower() in country.lower():
          possible.append(country)
      if len(possible) == 0:
        print("Unrecognized country.")
        print("")
      elif len(possible) > 1:
        print("Be more specific", possible)
        print("")
      else:
        goodCountry = possible[0]

      if goodCountry:
        self.map[goodCountry].printCountry()
        return
      else:
        return


    goodRes = 0
    islamRes = 0
    goodC = 0
    islamC = 0
    worldPos = 0
    for country in self.map:
      if self.map[country].type == "Shia-Mix" or self.map[country].type == "Suni":
        if self.map[country].governance == 1:
          goodC += 1
          goodRes += self.countryResources(country)
        elif self.map[country].governance == 2:
          goodC += 1
        elif self.map[country].governance == 3:
          islamC += 1
        elif self.map[country].governance == 4:
          islamC += 1
          islamRes += self.countryResources(country)
      elif self.map[country].type != "Iran" and self.map[country].name != "United States":
        if self.map[country].posture == "Hard":
          worldPos += 1
        elif self.map[country].posture == "Soft":
          worldPos -= 1
    print("")
    print("GOOD GOVERNANCE")
    num = 0
    for country in self.map:
      if self.map[country].type != "Non-Muslim" and self.map[country].governance == 1:
        num += 1
        self.map[country].printCountry()
    if not num:
      print("none")
    print("")
    print("FAIR GOVERNANCE")
    num = 0
    for country in self.map:
      if self.map[country].type != "Non-Muslim" and self.map[country].governance == 2:
        num += 1
        self.map[country].printCountry()
    if not num:
      print("none")
    print("")
    print("POOR GOVERNANCE")
    num = 0
    for country in self.map:
      if self.map[country].type != "Non-Muslim" and self.map[country].governance == 3:
        num += 1
        self.map[country].printCountry()
    if not num:
      print("none")
    print("")
    print("ISLAMIC RULE")
    num = 0
    for country in self.map:
      if self.map[country].type != "Non-Muslim" and self.map[country].governance == 4:
        num += 1
        self.map[country].printCountry()
    if not num:
      print("none")
    print("")
    print("HARD POSTURE")
    num = 0
    for country in self.map:
      if self.map[country].posture == "Hard":
        num += 1
        self.map[country].printCountry()
    if not num:
      print("none")
    print("")
    print("SOFT POSTURE")
    num = 0
    for country in self.map:
      if self.map[country].posture == "Soft":
        num += 1
        self.map[country].printCountry()
    if not num:
      print("none")
    print("")
    print("PLOTS")
    plotCountries = 0
    for country in self.map:
      if self.map[country].plots > 0:
        plotCountries += 1
        print("%s: %d plot(s)" % (country, self.map[country].plots))
    if plotCountries == 0:
      print("No Plots")
    print("")
    print("VICTORY")
    print("Good Resources   : %d" % goodRes)
    print("Islamic Resources: %d" % islamRes)
    print("---")
    print("Good/Fair Countries   : %d" % goodC)
    print("Poor/Islamic Countries: %d" % islamC)
    print("")
    print("GWOT")
    print("US Posture: %s" % self.map["United States"].posture)
    if worldPos > 0:
      worldPosStr = "Hard"
    elif worldPos < 0:
      worldPosStr = "Soft"
    else:
      worldPosStr = "Even"
    print("World Posture: %s %d" % (worldPosStr, abs(worldPos)))
    print("US Prestige: %d" % self.prestige)
    print("")
    print("TROOPS")
    if self.troops >= 10:
      print("Low Intensity: %d troops available" % self.troops)
    elif self.troops >= 5:
      print("War: %d troops available" % self.troops)
    else:
      print("Overstretch: %d troops available" % self.troops)
    print("")
    print("JIHADIST FUNDING")
    print("Funding: %d" % self.funding)
    print("Cells Available: %d" % self.cells)
    print("")
    print("EVENTS")
    if len(self.markers) == 0:
      print("Markers: None")
    else:
      print("Markers: %s" % ", ".join(self.markers))
    if len(self.lapsing) == 0:
      print("Lapsing: None")
    else:
      print("Lapsing: %s" % ", ".join(self.lapsing))
    print("")
    print("DATE")
    print("%d (Turn %s)" % (self.startYear + (self.turn - 1), self.turn))
    print("")

  def help_status(self):
    print("Display game status.  status [country] will print out status of single country.")
    print("")

  def do_sta(self, rest):
    self.do_status(rest)

  def help_sta(self):
    self.help_status()

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

  def do_his(self, rest):
    self.do_history(rest)

  def help_his(self):
    self.help_history()

  def do_deploy(self, rest):
    moveFrom = None
    available = 0
    while not moveFrom:
      input = self.getCountryFromUser("From what country (track for Troop Track) (? for list)?: ",  "track", self.listCountriesWithTroops)
      if input == "":
        print("")
        return
      elif input == "track":
        if self.troops <= 0:
          print("There are no troops on the Troop Track.")
          print("")
          return
        else:
          print("Deploy from Troop Track - %d available" % self.troops)
          print("")
          available = self.troops
          moveFrom = input
      else:
        if self.map[input].troops() <= 0:
          print("There are no troops in %s." % input)
          print("")
          return
        else:
          print("Deploy from %s = %d availalbe" % (input, self.map[input].troops()))
          print("")
          available = self.map[input].troops()
          moveFrom = input
    moveTo = None
    while not moveTo:
      input = self.getCountryFromUser("To what country (track for Troop Track)  (? for list)?: ",  "track", self.listDeployOptions)
      if input == "":
        print("")
        return
      elif input == "track":
        print("Deploy troops from %s to Troop Track" % moveFrom)
        print("")
        moveTo = input
      else:
        print("Deploy troops from %s to %s" % (moveFrom, input))
        print("")
        moveTo = input
    howMany = 0
    while not howMany:
      input = self.getNumTroopsFromUser("Deploy how many troops (%d available)? " % available, available)
      if input == "":
        print("")
        return
      else:
        howMany = input
    if moveFrom == "track":
      self.troops -= howMany
      troopsLeft = self.troops
    else:
      if self.map[moveFrom].regimeChange:
        if (self.map[moveFrom].troops() - howMany) < (5 + self.map[moveFrom].totalCells(True)):
          print("You cannot move that many troops from a Regime Change country.")
          print("")
          return
      self.map[moveFrom].changeTroops(-howMany)
      troopsLeft = self.map[moveFrom].troops()
    if moveTo == "track":
      self.troops += howMany
      troopsNow = self.troops
    else:
      self.map[moveTo].changeTroops(howMany)
      troopsNow = self.map[moveTo].troops()
    self.outputToHistory("* %d troops deployed from %s (%d) to %s (%d)" % (howMany, moveFrom, troopsLeft, moveTo, troopsNow))

  def help_deploy(self):
    print("Move Trops")
    print("")

  def do_dep(self, rest):
    self.do_deploy(rest)

  def help_dep(self):
    self.help_toops()

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
        if self.map[input].sleeper_cells + self.map[input].activeCells <= 0 and self.map[input].cadre <= 0:
          print("There are no cells or cadre in %s." % input)
          print("")
        elif "FATA" in self.map[input].markers and self.map[input].regimeChange == 0:
          print("No disrupt allowed due to FATA.")
          print("")
        elif self.map[input].troops() > 0 or self.map[input].type == "Non-Muslim" or self.map[input].alignment == "Ally":
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

  def do_dis(self, rest):
    self.do_disrupt(rest)

  def help_dis(self):
    self.help_disrupt()

  def do_woi(self, rest):
    where = None
    while not where:
      input = self.getCountryFromUser("War of Ideas in what country?  (? for list): ", "XXX", self.listWoICountries)
      if input == "":
        print("")
        return
      else:
        if self.map[input].type == "Non-Muslim" and input != "United States":
          where = input
        elif self.map[input].alignment == "Ally" or self.map[input].alignment == "Neutral" or self.map[input].governance == 0:
          where = input
        else:
          print("Country not eligible for War of Ideas.")
          print("")
    if self.map[where].type == "Non-Muslim" and input != "United States": # Non-Muslim
      postureRoll = self.getRollFromUser("Enter Posture Roll or r to have program roll: ")
      if postureRoll > 4:
        self.map[where].posture = "Hard"
        self.outputToHistory("* War of Ideas in %s - Posture Hard" % where)
        if self.map["United States"].posture == "Hard":
          self.prestige += 1
          if self.prestige > 12:
            self.prestige = 12
          self.outputToHistory("US Prestige now %d" % self.prestige)
      else:
        self.map[where].posture = "Soft"
        self.outputToHistory("* War of Ideas in %s - Posture Soft" % where)
        if self.map["United States"].posture == "Soft":
          self.prestige += 1
          if self.prestige > 12:
            self.prestige = 12
          self.outputToHistory("US Prestige now %d" % self.prestige)
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

  def do_alr(self, rest):
    self.do_alert(rest)

  def help_alr(self):
    self.help_alert()

  def do_reassessment(self, rest):
    self.handleReassessment()

  def help_reassessment(self):
    print("Reassessment of US Posture.")

  def do_rea(self, rest):
    self.do_reassessment(rest)

  def help_rea(self):
    self.help_reassessment()

  def do_regime(self, rest):
    if   self.map["United States"].posture == "Soft":
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
        if (self.map[input].governance == 4) or (input == "Iraq" and "Iraqi WMD" in self.markers) or (input == "Libya" and "Libyan WMD" in self.markers):
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
        if self.troops <= 6:
          print("There are not enough troops on the Troop Track.")
          print("")
          return
        else:
          print("Deploy from Troop Track - %d available" % self.troops)
          print("")
          available = self.troops
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

  def do_reg(self, rest):
    self.do_regime(rest)

  def help_reg(self):
    self.help_regime()

  def do_withdraw(self, rest):
    if   self.map["United States"].posture == "Hard":
      print("No Withdrawl with US Posture Hard")
      print("")
      return
    moveFrom = None
    available = 0
    while not moveFrom:
      input = self.getCountryFromUser("Withdrawl in what country?  (? for list): ", "XXX", self.listRegimeChangeCountries)
      if input == "":
        print("")
        return
      else:
        if self.map[input].regimeChange > 0:
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
        print("Withdraw troops from %s to Troop Track" % moveFrom)
        print("")
        moveTo = input
      else:
        print("Withdraw troops from %s to %s" % (moveFrom, input))
        print("")
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

  def do_wit(self, rest):
    self.do_withdraw(rest)

  def help_wit(self):
    self.help_withdraw()

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

  ''' test with timing system
  def do_j(self, rest):
    if self.phase != "Jihadist Action Phase":
      print("It is not the Jihadist Action Phase")
      print("")
      return
    if rest == "p" or rest == "pass":
      self.phase = "US Action Phase"
      self.outputToHistory("== Jihadist player passes turn. ==", True)
      return
    cardNum = None
    try:
      input = int(rest)
      if input < 1 or input > 120:
        print("Enter j then the card number or pass e.g. j 24 or j pass")
        print("")
        return
      else:
        cardNum = input
    except:
      print("Enter j then the card number or pass e.g. j 24 or j pass")
      print("")
      return
    self.jCard += 1
    self.outputToHistory("== Jihadist plays %s. ==" % self.deck[str(cardNum)].name, True)
    self.aiFlowChartTop(cardNum)
    if self.jCard
  '''

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
        if self.backlashInPlay and (self.map[country].type != 'Non-Muslim'):
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
        elif self.map[country].type != "Non-Muslim":
          if country != "Iran":
            numRolls = 0
            if plotType == "WMD":
              numRolls = 3
            else:
              numRolls = plotType
            for i in range(numRolls):
              govRolls.append(random.randint(1,6))
        elif self.map[country].type == "Non-Muslim":
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

  def do_turn(self, rest):
    self.SaveTurn()

    self.outputToHistory("* End of Turn.", False)
    if "Pirates" in self.markers and (self.map["Somalia"].governance == 4 or self.map["Yemen"].governance == 4):
      self.outputToHistory("No funding drop due to Pirates.", False)
    else:
      self.funding -= 1
      if self.funding < 1:
        self.funding = 1
      self.outputToHistory("Jihadist Funding now %d" % self.funding, False)
    anyIR = False
    for country in self.map:
      if self.map[country].governance == 4:
        anyIR = True
        break
    if anyIR:
      self.prestige -= 1
      if self.prestige < 1:
        self.prestige = 1
    self.outputToHistory("Islamic Rule - US Prestige now %d" % self.prestige, False)
    worldPos = 0
    for country in self.map:
      if not (self.map[country].type == "Shia-Mix" or self.map[country].type == "Suni") and self.map[country].type != "Iran" and self.map[country].name != "United States":
        if self.map[country].posture == "Hard":
          worldPos += 1
        elif self.map[country].posture == "Soft":
          worldPos -= 1
    if (self.map["United States"].posture == "Hard" and worldPos >= 3) or (self.map["United States"].posture == "Soft" and worldPos <= -3):
      self.prestige += 1
      if self.prestige > 12:
        self.prestige = 12
      self.outputToHistory("GWOT World posture is 3 and matches US - US Prestige now %d" % self.prestige, False)
    for event in self.lapsing:
      self.outputToHistory("%s has Lapsed." % event, False)
    self.lapsing = []
    goodRes = 0
    islamRes = 0
    goodC = 0
    islamC = 0
    worldPos = 0
    for country in self.map:
      if self.map[country].type == "Shia-Mix" or self.map[country].type == "Suni":
        if self.map[country].governance == 1:
          goodC += 1
          goodRes += self.countryResources(country)
        elif self.map[country].governance == 2:
          goodC += 1
        elif self.map[country].governance == 3:
          islamC += 1
        elif self.map[country].governance == 4:
          islamC += 1
          islamRes += self.countryResources(country)
    self.outputToHistory("---", False)
    self.outputToHistory("Good Resources   : %d" % goodRes, False)
    self.outputToHistory("Islamic Resources: %d" % islamRes, False)
    self.outputToHistory("---", False)
    self.outputToHistory("Good/Fair Countries   : %d" % goodC, False)
    self.outputToHistory("Poor/Islamic Countries: %d" % islamC, False)
    self.turn += 1
    self.outputToHistory("---", False)
    self.outputToHistory("", False)
    usCards = 0
    jihadistCards = 0
    if self.funding >= 7:
      jihadistCards = 9
    elif self.funding >= 4:
      jihadistCards = 8
    else:
      jihadistCards = 7
    if self.troops >= 10:
      usCards = 9
    elif self.troops >= 5:
      usCards = 8
    else:
      usCards = 7
    self.outputToHistory("Jihadist draws %d cards." % jihadistCards, False)
    self.outputToHistory("US draws %d cards." % usCards, False)
    self.outputToHistory("---", False)
    self.outputToHistory("", False)
    self.outputToHistory("[[ %d (Turn %s) ]]" % (self.startYear + (self.turn - 1), self.turn), False)

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
        print("Entry error")
        print("")


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

def main():
  print("")
  print("Labyrinth: The War on Terror AI Player")
  print("")
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
        print("Entry error")
        print("")

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
        print("Entry error")
        print("")

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
  main()
