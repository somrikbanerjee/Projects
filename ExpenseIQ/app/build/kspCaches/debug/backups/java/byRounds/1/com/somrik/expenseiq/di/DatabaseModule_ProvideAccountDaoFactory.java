package com.somrik.expenseiq.di;

import com.somrik.expenseiq.data.db.AppDatabase;
import com.somrik.expenseiq.data.db.dao.AccountDao;
import dagger.internal.DaggerGenerated;
import dagger.internal.Factory;
import dagger.internal.Preconditions;
import dagger.internal.QualifierMetadata;
import dagger.internal.ScopeMetadata;
import javax.annotation.processing.Generated;
import javax.inject.Provider;

@ScopeMetadata
@QualifierMetadata
@DaggerGenerated
@Generated(
    value = "dagger.internal.codegen.ComponentProcessor",
    comments = "https://dagger.dev"
)
@SuppressWarnings({
    "unchecked",
    "rawtypes",
    "KotlinInternal",
    "KotlinInternalInJava",
    "cast"
})
public final class DatabaseModule_ProvideAccountDaoFactory implements Factory<AccountDao> {
  private final Provider<AppDatabase> dbProvider;

  public DatabaseModule_ProvideAccountDaoFactory(Provider<AppDatabase> dbProvider) {
    this.dbProvider = dbProvider;
  }

  @Override
  public AccountDao get() {
    return provideAccountDao(dbProvider.get());
  }

  public static DatabaseModule_ProvideAccountDaoFactory create(Provider<AppDatabase> dbProvider) {
    return new DatabaseModule_ProvideAccountDaoFactory(dbProvider);
  }

  public static AccountDao provideAccountDao(AppDatabase db) {
    return Preconditions.checkNotNullFromProvides(DatabaseModule.INSTANCE.provideAccountDao(db));
  }
}
