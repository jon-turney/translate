#
# Copyright 2004-2006,2008-2009 Zuza Software Foundation
#
# This file is part of the Translate Toolkit.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.

"""Classes that hold units of .rc files (:class:`rcunit`) or entire files
(:class:`rcfile`) used in translating Windows Resources.

.. note:::

   This implementation is based mostly on observing WINE .rc files,
   these should mimic other non-WINE .rc files.
"""

import re

from pyparsing import (Combine, Forward, Group, Keyword, Optional, SkipTo, Word,
                       ZeroOrMore, OneOrMore, alphanums, alphas,
                       commaSeparatedList, cStyleComment, delimitedList, nums,
                       quotedString, removeQuotes, restOfLine)

from translate.storage import base


def escape_to_python(string):
    """Escape a given .rc string into a valid Python string."""
    pystring = re.sub('"\\s*\\\\\n\\s*"', "", string)   # xxx"\n"xxx line continuation
    pystring = re.sub("\\\\\\\n", "", pystring)         # backslash newline line continuation
    pystring = re.sub("\\\\n", "\n", pystring)          # Convert escaped newline to a real newline
    pystring = re.sub("\\\\t", "\t", pystring)          # Convert escape tab to a real tab
    pystring = re.sub("\\\\\\\\", "\\\\", pystring)     # Convert escape backslash to a real escaped backslash
    return pystring


def escape_to_rc(string):
    """Escape a given Python string into a valid .rc string."""
    rcstring = re.sub("\\\\", "\\\\\\\\", string)
    rcstring = re.sub("\t", "\\\\t", rcstring)
    rcstring = re.sub("\n", "\\\\n", rcstring)
    return rcstring


class rcunit(base.TranslationUnit):
    """A unit of an rc file"""

    def __init__(self, source="", **kwargs):
        """Construct a blank rcunit."""
        super().__init__(source)
        self.name = ""
        self._value = ""
        self.comments = []
        self.source = source
        self.match = None

    @property
    def source(self):
        return self._value

    @source.setter
    def source(self, source):
        """Sets the source AND the target to be equal"""
        self._rich_source = None
        self._value = source or ""

    @property
    def target(self):
        return self.source

    @target.setter
    def target(self, target):
        """.. note:: This also sets the ``.source`` attribute!"""
        self._rich_target = None
        self.source = target

    def __str__(self):
        """Convert to a string."""
        return self.getoutput()

    def getoutput(self):
        """Convert the element back into formatted lines for a .rc file."""
        if self.isblank():
            return "".join(self.comments + ["\n"])
        else:
            return "".join(self.comments + ["%s=%s\n" % (self.name, self.value)])

    def getlocations(self):
        return [self.name]

    def addnote(self, text, origin=None, position="append"):
        self.comments.append(text)

    def getnotes(self, origin=None):
        return '\n'.join(self.comments)

    def removenotes(self, origin=None):
        self.comments = []

    def isblank(self):
        """Returns whether this is a blank element, containing only comments."""
        return not (self.name or self.value)


def rc_statement():
    """
    Generate a RC statement parser that can be used to parse a RC file

    :rtype: pyparsing.ParserElement
    """

    one_line_comment = '//' + restOfLine

    comments = cStyleComment ^ one_line_comment

    precompiler = Word('#', alphanums) + restOfLine

    language_definition = "LANGUAGE" + Word(alphas + '_').setResultsName(
        "language") + Optional(',' + Word(alphas + '_').setResultsName("sublanguage"))

    block_start = (Keyword('{') | Keyword("BEGIN")).setName("block_start")
    block_end = (Keyword('}') | Keyword("END")).setName("block_end")

    reserved_words = block_start | block_end

    name_id = ~reserved_words + \
        Word(alphas, alphanums + '_').setName("name_id")

    numbers = Word(nums)

    integerconstant = numbers ^ Combine('0x' + numbers)

    constant = Combine(
        Optional(Keyword("NOT")) + (name_id | integerconstant), adjacent=False, joinString=' ')

    combined_constants = delimitedList(constant, '|')

    block_options = Optional(SkipTo(
        Keyword("CAPTION"), failOn=block_start)("pre_caption") + Keyword("CAPTION") + quotedString("caption")) + SkipTo(block_start)("post_caption")

    string = quotedString().setParseAction(removeQuotes)
    quotedStringSequence = Combine(OneOrMore(string), adjacent=False).setParseAction(lambda toks: ['"' + t + '"' for t in toks])

    undefined_control = Group(name_id.setResultsName(
        "id_control") + delimitedList(quotedStringSequence ^ constant ^ numbers ^ Group(combined_constants)).setResultsName("values_"))

    block = block_start + \
        ZeroOrMore(undefined_control)("controls") + block_end

    dialog = name_id(
        "block_id") + (Keyword("DIALOGEX") | Keyword("DIALOG"))("block_type") + block_options + block

    string_table = Keyword("STRINGTABLE")(
        "block_type") + block_options + block

    menu_item = Keyword(
        "MENUITEM")("block_type") + (commaSeparatedList("values_") | Keyword("SEPARATOR"))

    popup_block = Forward()

    popup_block <<= Group(Keyword("POPUP")("block_type") + Optional(quotedString("caption")) + block_start +
                          ZeroOrMore(Group(menu_item | popup_block))("elements") + block_end)("popups*")

    menu = name_id("block_id") + \
        Keyword("MENU")("block_type") + block_options + \
        block_start + ZeroOrMore(popup_block) + block_end

    statem = comments ^ precompiler ^ language_definition ^ dialog ^ string_table ^ menu

    return statem


def generate_stringtable_name(identifier):
    """Return the name generated for a stringtable element."""
    return "STRINGTABLE." + identifier


def generate_menu_pre_name(block_type, block_id):
    """Return the pre-name generated for elements of a menu."""
    return "%s.%s" % (block_type, block_id)


def generate_popup_pre_name(pre_name, caption):
    """Return the pre-name generated for subelements of a popup.

    :param pre_name: The pre_name that already have the popup.
    :param caption: The caption (whitout quotes) of the popup.

    :return: The subelements pre-name based in the pre-name of the popup and
             its caption.
    """
    return "%s.%s" % (pre_name, caption.replace(" ", "_"))


def generate_popup_caption_name(pre_name):
    """Return the name generated for a caption of a popup."""
    return "%s.POPUP.CAPTION" % (pre_name)


def generate_menuitem_name(pre_name, block_type, identifier):
    """Return the name generated for a menuitem of a popup."""
    return "%s.%s.%s" % (pre_name, block_type, identifier)


def generate_dialog_caption_name(block_type, identifier):
    """Return the name generated for a caption of a dialog."""
    return "%s.%s.%s" % (block_type, identifier, "CAPTION")


def generate_dialog_control_name(block_type, block_id, control_type, identifier):
    """Return the name generated for a control of a dialog."""
    return "%s.%s.%s.%s" % (block_type, block_id, control_type, identifier)


class rcfile(base.TranslationStore):
    """This class represents a .rc file, made up of rcunits."""

    UnitClass = rcunit
    default_encoding = "cp1252"

    def __init__(self, inputfile=None, lang=None, sublang=None, **kwargs):
        """Construct an rcfile, optionally reading in from inputfile."""
        super().__init__(**kwargs)
        self.filename = getattr(inputfile, 'name', '')
        self.lang = lang
        self.sublang = sublang
        if inputfile is not None:
            rcsrc = inputfile.read()
            inputfile.close()
            self.parse(rcsrc)

    def add_popup_units(self, pre_name, popup):
        """Transverses the popup tree making new units as needed."""

        if popup.caption:
            newunit = rcunit(escape_to_python(popup.caption[1:-1]))
            newunit.name = generate_popup_caption_name(pre_name)
            newunit.match = popup
            self.addunit(newunit)

        for element in popup.elements:

            if element.block_type and element.block_type == "MENUITEM":

                if element.values_ and len(element.values_) >= 2:
                    newunit = rcunit(escape_to_python(element.values_[0][1:-1]))
                    newunit.name = generate_menuitem_name(pre_name, element.block_type, element.values_[1])
                    newunit.match = element
                    self.addunit(newunit)
                # Else it can be a separator.
            elif element.popups:
                for sub_popup in element.popups:
                    self.add_popup_units(generate_popup_pre_name(pre_name, popup.caption[1:-1]), sub_popup)

    def parse(self, rcsrc):
        """Read the source of a .rc file in and include them as units."""
        self.encoding = "auto"
        rcsrc, self.encoding = self.detect_encoding(rcsrc, default_encodings=[self.default_encoding])

        rcsrc = rcsrc.replace('\r', '')

        # Parse the strings into a structure.
        results = rc_statement().searchString(rcsrc)

        processblocks = True

        for statement in results:
            if statement.language:

                if self.lang is None or statement.language == self.lang:
                    if self.sublang is None or statement.sublanguage == self.sublang:
                        self.lang = statement.language
                        self.sublang = statement.sublanguage
                        processblocks = True
                    else:
                        processblocks = False
                else:
                    processblocks = False
                continue

            if processblocks and statement.block_type:

                if statement.block_type in ("DIALOG", "DIALOGEX"):

                    if statement.caption:
                        newunit = rcunit(escape_to_python(statement.caption[1:-1]))
                        newunit.name = generate_dialog_caption_name(statement.block_type, statement.block_id[0])
                        newunit.match = statement
                        self.addunit(newunit)

                    for control in statement.controls:

                        if control.id_control[0] in ("AUTOCHECKBOX AUTORADIOBUTTON CAPTION CHECKBOX CTEXT CONTROL DEFPUSHBUTTON GROUPBOX LTEXT PUSHBUTTON RADIOBUTTON RTEXT")\
                                and (control.values_[0].startswith('"') or control.values_[0].startswith("'")):

                            # The first value without quoted chars.
                            escaped_value = escape_to_python(control.values_[0][1:-1])
                            newunit = rcunit(escaped_value)
                            newunit.name = generate_dialog_control_name(statement.block_type, statement.block_id[0], control.id_control[0], control.values_[1])
                            newunit.match = control
                            self.addunit(newunit)

                    continue

                if statement.block_type in ("MENU"):

                    pre_name = generate_menu_pre_name(statement.block_type, statement.block_id[0])

                    for popup in statement.popups:

                        self.add_popup_units(pre_name, popup)

                    continue

                if statement.block_type in ("STRINGTABLE"):

                    for text in statement.controls:

                        newunit = rcunit(escape_to_python(text.values_[0][1:-1]))
                        newunit.name = generate_stringtable_name(text.id_control[0])
                        newunit.match = text
                        self.addunit(newunit)

                    continue

    def serialize(self, out):
        """Write the units back to file."""
        out.write(("".join(self.blocks)).encode(self.encoding))
