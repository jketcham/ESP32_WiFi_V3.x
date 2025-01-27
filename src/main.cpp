/*
 * Copyright (c) 2015-2016 Chris Howell
 *
 * -------------------------------------------------------------------
 *
 * Additional Adaptation of OpenEVSE ESP Wifi
 * by Trystan Lea, Glyn Hudson, OpenEnergyMonitor
 * All adaptation GNU General Public License as below.
 *
 * -------------------------------------------------------------------
 *
 * This file is part of Open EVSE.
 * Open EVSE is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3, or (at your option)
 * any later version.
 * Open EVSE is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * You should have received a copy of the GNU General Public License
 * along with Open EVSE; see the file COPYING.  If not, write to the
 * Free Software Foundation, Inc., 59 Temple Place - Suite 330,
 * Boston, MA 02111-1307, USA.
 */

#include <Arduino.h>
#include <WiFiUdp.h>
#include <ArduinoOTA.h>               // local OTA update from Arduino IDE
#include <MongooseCore.h>

#include "emonesp.h"
#include "config.h"
#include "net_manager.h"
#include "web_server.h"
#include "ohm.h"
#include "input.h"
#include "emoncms.h"
#include "mqtt.h"
#include "divert.h"
#include "ota.h"
#include "lcd.h"
#include "openevse.h"
#include "root_ca.h"
#include "hal.h"

#include "RapiSender.h"

RapiSender rapiSender(&RAPI_PORT);

unsigned long Timer1; // Timer for events once every 30 seconds
unsigned long Timer3; // Timer for events once every 2 seconds

boolean rapi_read = 0; //flag to indicate first read of RAPI status

// -------------------------------------------------------------------
// SETUP
// -------------------------------------------------------------------
void setup()
{
  HAL.begin();

  DEBUG.println();
  DEBUG.print("OpenEVSE WiFI ");
  DEBUG.println(HAL.getShortId());
  DEBUG.println("Firmware: " + currentfirmware);

  DEBUG.printf("Free: %d\n", HAL.getFreeHeap());

  // Read saved settings from the config
  config_load_settings();
  DBUGF("After config_load_settings: %d", HAL.getFreeHeap());

  // Initialise the WiFi
  net_setup();
  DBUGF("After net_setup: %d", HAL.getFreeHeap());

  // Initialise Mongoose networking library
  Mongoose.begin();
  Mongoose.setRootCa(root_ca);

  // Bring up the web server
  web_server_setup();
  DBUGF("After web_server_setup: %d", HAL.getFreeHeap());

#ifdef ENABLE_OTA
  ota_setup();
  DBUGF("After ota_setup: %d", HAL.getFreeHeap());
#endif

  rapiSender.setOnEvent(on_rapi_event);
  rapiSender.enableSequenceId(0);
} // end setup

// -------------------------------------------------------------------
// LOOP
// -------------------------------------------------------------------
void
loop() {
  Profile_Start(loop);

  Profile_Start(Mongoose);
  Mongoose.poll(0);
  Profile_End(Mongoose, 10);

  lcd_loop();
  web_server_loop();
  net_loop();
#ifdef ENABLE_OTA
  ota_loop();
#endif
  rapiSender.loop();
  divert_current_loop();

  if(OPENEVSE_STATE_STARTING != state &&
     OPENEVSE_STATE_INVALID != state)
  {
    // Read initial state from OpenEVSE
    if (rapi_read == 0)
    {
      lcd_display(F("OpenEVSE WiFI"), 0, 0, 0, LCD_CLEAR_LINE);
      lcd_display(currentfirmware, 0, 1, 5 * 1000, LCD_CLEAR_LINE);
      lcd_loop();

      DBUGLN("first read RAPI values");
      handleRapiRead(); //Read all RAPI values
      rapi_read=1;
    }

    // -------------------------------------------------------------------
    // Do these things once every 2s
    // -------------------------------------------------------------------
    if ((millis() - Timer3) >= 2000) {
      DEBUG.printf("Free: %d\n", HAL.getFreeHeap());
      update_rapi_values();
      Timer3 = millis();
    }
  }
  else
  {
    // Check if we can talk to OpenEVSE
    if ((millis() - Timer3) >= 1000)
    {
      // Check state the OpenEVSE is in.
      rapiSender.sendCmd("$GS", [](int ret) {
        if (RAPI_RESPONSE_OK == ret)
        {
          if(rapiSender.getTokenCnt() >= 3)
          {
            const char *val = rapiSender.getToken(1);
            DBUGVAR(val);
            state = strtol(val, NULL, 10);
            DBUGVAR(state);
          }
        } else {
          DBUGLN("OpenEVSE not responding or not connected");
        }
      });
      Timer3 = millis();
    }
  }

  if(net_is_connected())
  {
    if (config_mqtt_enabled()) {
      mqtt_loop();
    }

    // -------------------------------------------------------------------
    // Do these things once every 30 seconds
    // -------------------------------------------------------------------
    if ((millis() - Timer1) >= 30000) {
      DBUGLN("Time1");

      if(!Update.isRunning())
      {
        String data;
        create_rapi_json(data); // create JSON Strings for EmonCMS and MQTT
        if (config_emoncms_enabled()) {
          emoncms_publish(data);
        }
        if (config_mqtt_enabled()) {
          mqtt_publish(data);
        }
        if(config_ohm_enabled()) {
          ohm_loop();
        }
      }

      Timer1 = millis();
    }
  } // end WiFi connected

  Profile_End(loop, 10);
} // end loop


void event_send(String event)
{
  web_server_event(event);

  if (config_mqtt_enabled()) {
    mqtt_publish(event);
  }
}
