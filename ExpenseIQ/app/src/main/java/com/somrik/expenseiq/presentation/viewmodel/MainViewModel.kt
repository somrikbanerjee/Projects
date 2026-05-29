package com.somrik.expenseiq.presentation.viewmodel

import androidx.lifecycle.ViewModel
import com.somrik.expenseiq.data.pref.SettingsManager
import com.somrik.expenseiq.data.pref.ThemeMode
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import javax.inject.Inject

@HiltViewModel
class MainViewModel @Inject constructor(
    settingsManager: SettingsManager
) : ViewModel() {
    val themeMode: StateFlow<ThemeMode> = settingsManager.themeMode
}
