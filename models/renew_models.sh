#!/usr/bin/env bash
sqlacodegen --noviews --noconstraints --outfile=models.py mysql+mysqlconnector://root:root@192.168.1.205:3306/guigong1121
